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
    "by the user, including each paper's DOI, title, and citation count. Return only "
    'valid JSON with exactly this shape: {"answer": "brief answer", "citations": '
    '[{"doi": "10.xxxx/...", "title": "paper title", "citation_count": 0}]}.'
)

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


NAIVE = naive
