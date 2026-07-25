"""Compact, deterministic evidence extraction from MCP tool responses."""
import json
import re
import unicodedata

from .validation import normalize_doi


_WHITESPACE = re.compile(r"\s+")


def normalize_title(value):
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    return _WHITESPACE.sub(" ", normalized).strip().casefold()


def _result_records(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    data = payload.get("data")
    scopes = [data, payload]
    for scope in scopes:
        if not isinstance(scope, dict):
            continue
        for key in ("results", "datasets", "products", "items", "nodes"):
            records = scope.get(key)
            if isinstance(records, list):
                return records
        if any(key in scope for key in ("doi", "title", "citations")):
            return [scope]
    return []


def _citation_count(record):
    for key in ("citations", "citation_count"):
        if key in record:
            return record.get(key)
    metrics = record.get("metrics")
    if isinstance(metrics, dict):
        return metrics.get("citation_count")
    return None


def extract_tool_evidence(text):
    """Return only the fields needed to audit the final citation records."""
    if not isinstance(text, str) or not text.strip():
        return []
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []

    evidence = []
    for record in _result_records(payload):
        if not isinstance(record, dict):
            continue
        row = {
            "doi": record.get("doi"),
            "title": record.get("title"),
            "citation_count": _citation_count(record),
        }
        if any(value is not None for value in row.values()):
            evidence.append(row)
    return evidence


def grounding_for(citation, ledger):
    """Compare one emitted citation with all evidence for the same DOI."""
    if not isinstance(citation, dict):
        return {
            "doi_grounded": False,
            "title_agrees": False,
            "citation_count_agrees": False,
            "record_grounded": False,
        }

    target_doi = normalize_doi(citation.get("doi"))
    matches = [
        row for row in ledger
        if normalize_doi(row.get("doi")) == target_doi and target_doi
    ]
    title = normalize_title(citation.get("title"))
    count = citation.get("citation_count")
    title_agrees = any(normalize_title(row.get("title")) == title for row in matches)
    count_agrees = any(row.get("citation_count") == count for row in matches)
    record_grounded = any(
        normalize_title(row.get("title")) == title
        and row.get("citation_count") == count
        for row in matches
    )
    return {
        "doi_grounded": bool(matches),
        "title_agrees": title_agrees,
        "citation_count_agrees": count_agrees,
        "record_grounded": record_grounded,
    }
