"""Context configurations for the citation-retrieval intervention."""
import json
from dataclasses import dataclass

from . import config
from .mcp_client import MCP


@dataclass(frozen=True)
class Context:
    name: str
    system_prompt: str
    tools: list


OUTPUT_CONTRACT = """\
OUTPUT CONTRACT
A successful response must be one raw JSON object with exactly two top-level
keys, "answer" and "citations". The citations array must contain exactly five
distinct objects, each with exactly these keys:
{"doi":"10.xxxx/...","title":"paper title","citation_count":0}
Every DOI and title must be a non-empty string copied from successful OpenAIRE
tool evidence, and every citation_count must be a non-negative integer copied
from that evidence. Never emit null. Skip records without a DOI and continue
down the ranked results. Do not add Markdown fences, a preamble, headings,
tables, notes, or any text before or after the JSON object.

If five complete, grounded records remain impossible after the allowed search
attempts, return the same two top-level keys with an empty citations array and
briefly explain the evidence shortage in "answer". This is a safe abstention,
not a successful five-citation response.\
"""


NAIVE_PROMPT = (
    "You are a research assistant with access to the OpenAIRE research graph. "
    "Use the provided tools to identify the five most influential papers requested "
    "by the user, including each paper's DOI, title, and citation count.\n\n"
    + OUTPUT_CONTRACT
)

ENGINEERED_PROMPT = """\
ROLE
You are an evidence-retrieval agent operating only on OpenAIRE tool evidence.

RETRIEVAL PROCEDURE
1. OpenAIRE combines plain query terms with AND: every extra term narrows the
result set. Start with the topic's 2-3 essential keywords; never expand it with
lists of synonyms.
2. Search with page_size=10, detail="minimal", and citationCount DESC. Minimal
results already contain DOI, title, and citation count; use them directly when
at least five complete DOI-bearing records are available. Prefer influence
class C3 only when field/age-normalized impact is specifically useful.
3. Skip incomplete records and continue down the ranked results. If fewer than
five complete records are available, remove query terms and retry. Make at most
two shorter-query retries.
4. Request detail="standard" only when a candidate has a DOI but another
required field is missing. Never emit a DOI, title, or count that did not appear
in a successful tool result in this conversation.

""" + OUTPUT_CONTRACT

_SCHEMA_CACHE = config.CACHE / "openaire_tool_schemas.json"
_NAIVE_TOOL_NAMES = (config.T_SEARCH, config.T_INFLUENCE)


def _live_tool_schemas():
    if _SCHEMA_CACHE.exists():
        try:
            cached = json.loads(_SCHEMA_CACHE.read_text())
            if isinstance(cached, list) and cached:
                return cached
        except (json.JSONDecodeError, OSError):
            pass
    tools = MCP().list_tools()
    _SCHEMA_CACHE.write_text(json.dumps(tools, sort_keys=True))
    return tools


def _openai_tool(tool):
    """Translate only the MCP envelope; preserve its input schema verbatim."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get(
                "inputSchema", {"type": "object", "properties": {}}
            ),
        },
    }


def naive():
    by_name = {tool.get("name"): tool for tool in _live_tool_schemas()}
    missing = [name for name in _NAIVE_TOOL_NAMES if name not in by_name]
    if missing:
        raise RuntimeError(f"OpenAIRE schemas missing required tools: {missing}")
    tools = [_openai_tool(by_name[name]) for name in _NAIVE_TOOL_NAMES]

    # This assertion protects the central fairness promise: the baseline sees
    # the full, real 43-parameter search schema, not a hand-pruned strawman.
    search_schema = tools[0]["function"]["parameters"]
    if len(search_schema.get("properties", {})) != 43:
        raise RuntimeError("live OpenAIRE search schema is no longer 43 parameters")
    return Context("naive", NAIVE_PROMPT, tools)


def engineered():
    search = {
        "type": "function",
        "function": {
            "name": config.T_SEARCH,
            "description": (
                "Search OpenAIRE research products. Query terms use strict AND "
                "logic: more terms produce fewer results, so begin with 2-3 "
                "essential keywords and shorten a query that yields fewer than "
                'five complete records. Use detail="minimal" directly when it '
                "contains DOI, title, and citation count; request standard only "
                "when a required field is missing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "2-3 essential keywords combined with AND. Drop "
                            "terms, never add synonyms, after zero results."
                        ),
                    },
                    "page_size": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "description": "Number of results; use 10 when ranking five.",
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["citationCount DESC"],
                        "description": "Rank most-cited records first.",
                    },
                    "detail": {
                        "type": "string",
                        "enum": ["minimal", "standard"],
                        "description": (
                            "Use minimal for routing and final citations when DOI, "
                            "title, and count are present; standard only to fill a "
                            "missing required field."
                        ),
                    },
                    "influence_class": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["C3"]},
                        "description": "Optional top-1% influence filter.",
                    },
                },
                "required": ["query"],
            },
        },
    }
    influence = {
        "type": "function",
        "function": {
            "name": config.T_INFLUENCE,
            "description": (
                "Find field- and age-normalized influential OpenAIRE records. "
                "C3 is the useful top-1% default; C1/C2 are often empty for "
                "niche topics. Query terms use strict AND logic, so shorten a "
                "zero-result query."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "influence_class": {
                        "type": "string",
                        "enum": ["C3"],
                        "description": "Use C3 (top 1%).",
                    },
                    "query": {
                        "type": "string",
                        "description": "2-3 essential AND-combined keywords.",
                    },
                    "page_size": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "description": "Number of results; use 10.",
                    },
                },
                "required": ["influence_class", "query"],
            },
        },
    }
    return Context("engineered", ENGINEERED_PROMPT, [search, influence])


NAIVE = naive
ENGINEERED = engineered
