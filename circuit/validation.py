"""Deterministic output extraction and contract validation.

Extraction never repairs JSON. It either parses the complete response or
recovers one independently parseable JSON object from surrounding text.
"""
import json
import re
from dataclasses import dataclass


TOP_LEVEL_KEYS = frozenset({"answer", "citations"})
CITATION_KEYS = frozenset({"doi", "title", "citation_count"})
_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)


@dataclass(frozen=True)
class Extraction:
    raw_parseable: bool
    method: str
    value: object = None
    error: str = None


def _balanced_object_spans(text):
    """Yield top-level brace spans while respecting JSON string escapes."""
    start = None
    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if depth == 0:
            if char == "{":
                start = index
                depth = 1
                in_string = False
                escaped = False
            continue

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                yield start, index + 1
                start = None


def _is_fenced(text, start, end):
    before = text[:start]
    after = text[end:]
    return bool(
        re.search(r"```(?:json)?\s*$", before, re.I)
        and re.match(r"\s*```", after)
    )


def extract_json(text):
    """Return raw or uniquely recoverable JSON without modifying its contents."""
    if not isinstance(text, str):
        return Extraction(False, "missing", error="response is not a string")

    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raw_error = f"{type(exc).__name__}: {exc}"
    else:
        return Extraction(True, "raw", value=value)

    candidates = []
    for start, end in _balanced_object_spans(text):
        try:
            value = json.loads(text[start:end])
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, dict):
            candidates.append((start, end, value))

    if len(candidates) == 1:
        start, end, value = candidates[0]
        method = "fenced" if _is_fenced(text, start, end) else "embedded"
        return Extraction(False, method, value=value, error=raw_error)
    if len(candidates) > 1:
        return Extraction(
            False,
            "ambiguous",
            error=f"{raw_error}; found {len(candidates)} parseable JSON objects",
        )
    return Extraction(False, "missing", error=raw_error)


def normalize_doi(value):
    if not isinstance(value, str):
        return ""
    return _DOI_PREFIX.sub("", value.strip()).rstrip(".,;").lower()


def validate_contract(value, expected_citations=5):
    """Return stable error codes for violations of the successful output shape."""
    errors = []
    if not isinstance(value, dict):
        return ["top_level:not_object"]

    if set(value) != TOP_LEVEL_KEYS:
        errors.append("top_level:keys")

    answer = value.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        errors.append("answer:nonempty_string")

    citations = value.get("citations")
    if not isinstance(citations, list):
        return errors + ["citations:list"]
    if len(citations) != expected_citations:
        errors.append(f"citations:length_{expected_citations}")

    normalized_dois = []
    for index, citation in enumerate(citations):
        prefix = f"citations[{index}]"
        if not isinstance(citation, dict):
            errors.append(f"{prefix}:object")
            continue
        if set(citation) != CITATION_KEYS:
            errors.append(f"{prefix}:keys")

        raw_doi = citation.get("doi")
        if not isinstance(raw_doi, str) or not raw_doi.strip():
            errors.append(f"{prefix}.doi:nonempty_string")
        else:
            normalized_dois.append(normalize_doi(raw_doi))

        title = citation.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{prefix}.title:nonempty_string")

        count = citation.get("citation_count")
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
        ):
            errors.append(f"{prefix}.citation_count:nonnegative_integer")

    if len(normalized_dois) != len(set(normalized_dois)):
        errors.append("citations:distinct_dois")
    return errors


def is_safe_abstention(value):
    """A grounded failure mode; deliberately not successful contract compliance."""
    return (
        isinstance(value, dict)
        and set(value) == TOP_LEVEL_KEYS
        and isinstance(value.get("answer"), str)
        and bool(value["answer"].strip())
        and value.get("citations") == []
    )


def citation_objects(value, limit=5):
    if not isinstance(value, dict) or not isinstance(value.get("citations"), list):
        return []
    return [
        item
        for item in value["citations"][:limit]
        if isinstance(item, dict)
    ]


def _matches_type(value, expected):
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: (
            isinstance(item, (int, float)) and not isinstance(item, bool)
        ),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    check = checks.get(expected)
    return True if check is None else check(value)


def validate_schema_instance(value, schema, path="$"):
    """Validate the JSON Schema subset used by the OpenAIRE tool definitions."""
    if not isinstance(schema, dict):
        return []

    errors = []
    if "allOf" in schema:
        for branch in schema["allOf"]:
            errors.extend(validate_schema_instance(value, branch, path))

    if "anyOf" in schema:
        branch_errors = [
            validate_schema_instance(value, branch, path)
            for branch in schema["anyOf"]
        ]
        if not any(not branch for branch in branch_errors):
            errors.append(f"{path}:anyOf")
            return errors

    if "oneOf" in schema:
        matches = sum(
            not validate_schema_instance(value, branch, path)
            for branch in schema["oneOf"]
        )
        if matches != 1:
            errors.append(f"{path}:oneOf")
            return errors

    expected_type = schema.get("type")
    if expected_type:
        types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_matches_type(value, item) for item in types):
            errors.append(f"{path}:type")
            return errors

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}:enum")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in value:
                errors.append(f"{path}.{required}:required")
        for key, item in value.items():
            if key in properties:
                errors.extend(
                    validate_schema_instance(item, properties[key], f"{path}.{key}")
                )
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{key}:additional_property")

    if isinstance(value, list):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            errors.append(f"{path}:minItems")
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            errors.append(f"{path}:maxItems")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(
                    validate_schema_instance(item, item_schema, f"{path}[{index}]")
                )

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}:minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}:maximum")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}:minLength")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}:pattern")

    return errors
