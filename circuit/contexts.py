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
Every DOI and title must be a non-empty string, and every citation_count must be
a non-negative integer. Never emit null. Do not add Markdown fences, a preamble,
headings, tables, notes, or any text before or after the JSON object.

If five complete records remain impossible, return the same two top-level keys
with an empty citations array and briefly explain the shortage in "answer".
This is a safe abstention, not a successful five-citation response.\
"""

RETRIEVAL_EVIDENCE_RULES = """\
EVIDENCE RULES
Every DOI, title, and citation_count must be copied from successful OpenAIRE
tool evidence in this conversation. Never fill a missing field from model
memory. Skip records without a DOI and continue down the ranked results.\
"""

NAIVE_PROMPT = (
    "You are a research assistant with access to the OpenAIRE research graph. "
    "Use the provided tools to identify the five most influential papers requested "
    "by the user, including each paper's DOI, title, and citation count.\n\n"
    + RETRIEVAL_EVIDENCE_RULES
    + "\n\n"
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
at least five complete DOI-bearing records are available.
3. Skip incomplete records and continue down the ranked results. If fewer than
five complete records are available, remove query terms and retry. Make at most
two shorter-query retries.
4. Request detail="standard" only when a candidate has a DOI but another
required field is missing. Never emit a DOI, title, or count that did not appear
in a successful tool result in this conversation.

""" + RETRIEVAL_EVIDENCE_RULES + "\n\n" + OUTPUT_CONTRACT

INTRINSIC_PROMPT = """\
ROLE
You are a research assistant answering only from knowledge stored in the model.
You have no tools or external sources and must not claim to have searched,
browsed, retrieved, or verified information.

KNOWLEDGE-ONLY PROCEDURE
Identify the five most influential papers requested by the user from intrinsic
knowledge alone. Do not invent a DOI or title. If you cannot confidently recall
five papers, return an empty citations array rather than guessing. Citation
counts change over time and cannot be looked up in this condition, so provide
your best integer estimate.

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
                },
                "required": ["query", "page_size", "sort_by", "detail"],
            },
        },
    }
    return Context("engineered", ENGINEERED_PROMPT, [search])


def intrinsic():
    return Context("intrinsic", INTRINSIC_PROMPT, [])


NAIVE = naive
ENGINEERED = engineered
INTRINSIC = intrinsic
