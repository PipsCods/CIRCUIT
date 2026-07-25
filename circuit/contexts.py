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


NAIVE_PROMPT = (
    "You are a research assistant with access to the OpenAIRE research graph. "
    "Use the provided tools to identify the five most influential papers requested "
    "by the user, including each paper's DOI, title, and citation count. Your entire "
    "final response must be one raw JSON object with exactly this shape: "
    '{"answer": "brief answer", "citations": [{"doi": "10.xxxx/...", '
    '"title": "paper title", "citation_count": 0}]}. Do not add Markdown fences, '
    "a preamble, headings, tables, notes, or any text before or after the JSON object."
)

ENGINEERED_PROMPT = """\
ROLE
You are an evidence-retrieval agent operating only on OpenAIRE tool evidence.

RETRIEVAL PROCEDURE
1. OpenAIRE combines plain query terms with AND: every extra term narrows the
result set. Start with the topic's 2-3 essential keywords; never expand it with
lists of synonyms.
2. Route cheaply with detail="minimal". Prefer citationCount DESC for raw
impact and influence class C3 for field/age-normalized impact.
3. If a tool call returns zero results or an error, remove query terms and retry.
Make at most two shorter-query retries. If evidence is still insufficient,
return an empty citations list rather than guessing.
4. Once a query works, request detail="standard" and select five records with
DOI, title, and citation count. Never emit a DOI that did not appear in a tool
result in this conversation.

OUTPUT CONTRACT
Your entire final response must be one raw JSON object with exactly this shape:
{"answer":"brief evidence-grounded answer","citations":[{"doi":"10.xxxx/...",
"title":"paper title","citation_count":0}]}
Use an integer citation_count. Do not add Markdown fences, a preamble, headings,
tables, notes, or any text before or after the JSON object.\
"""

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
                "essential keywords and shorten a zero-result query. Use "
                'detail="minimal" while routing, then detail="standard" for '
                "records that may be cited."
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
                            "Use minimal to test/rank a query; standard only "
                            "when collecting final citation evidence."
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
