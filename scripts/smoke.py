#!/usr/bin/env python3
"""The access check. Run this before writing any experiment code.

Verifies every external dependency the harness relies on, and — importantly —
verifies that the premise of the whole project actually reproduces: that a
naively over-specified OpenAIRE query returns zero results.
"""
import json
import sys
import pathlib
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from circuit import config, llm  # noqa: E402
from circuit.mcp_client import MCP  # noqa: E402

RESULTS = []


def check(name):
    def deco(fn):
        def run():
            try:
                detail = fn()
                RESULTS.append((True, name, detail or ""))
                print(f"  PASS  {name}" + (f"  |  {detail}" if detail else ""))
            except Exception as e:
                RESULTS.append((False, name, str(e)))
                print(f"  FAIL  {name}\n          {type(e).__name__}: {e}")
        return run
    return deco


@check("OPENROUTER_API_KEY is set")
def c_key():
    if not config.OPENROUTER_KEY:
        raise RuntimeError("missing — copy .env.example to .env and fill it in")
    return f"...{config.OPENROUTER_KEY[-6:]}"


@check("price table matches live OpenRouter pricing")
def c_prices():
    with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=60) as r:
        live = {m["id"]: m.get("pricing", {}) for m in json.load(r)["data"]}
    drift = []
    for model, p in config.PRICES.items():
        if model not in live:
            raise RuntimeError(f"{model} not offered by OpenRouter any more")
        for ours, theirs in (("in", "prompt"), ("out", "completion")):
            got = float(live[model][theirs])
            if abs(got - p[ours]) > 1e-12:
                drift.append(f"{model}.{ours}: ours={p[ours]} live={got}")
    if drift:
        raise RuntimeError("update config.PRICES — " + "; ".join(drift))
    return f"{len(config.PRICES)} models verified"


@check("Gemma 4 responds")
def c_small():
    r = llm.chat(config.SMALL, [{"role": "user", "content": "Reply with the word OK."}],
                 max_tokens=16)
    if "ok" not in r.text.lower():
        raise RuntimeError(f"unexpected reply: {r.text!r}")
    return f"{r.tokens_in}+{r.tokens_out} tok, ${r.cost:.8f}"


@check("Gemma 4 emits a well-formed tool call")
def c_small_tools():
    tools = [{
        "type": "function",
        "function": {
            "name": "search_research_products",
            "description": "Search the OpenAIRE research graph for papers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords."},
                    "page_size": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    }]
    r = llm.chat(
        config.SMALL,
        [{"role": "user", "content": "Find papers about CRISPR gene editing. Use the tool."}],
        tools=tools, max_tokens=256)
    if not r.tool_calls:
        raise RuntimeError("no tool_calls returned — the harness must fall back to "
                           "prompt-emitted JSON tool specs instead of native calling")
    c = r.tool_calls[0]
    if "__malformed__" in c["args"]:
        raise RuntimeError(f"malformed tool arguments: {c['args']['__malformed__'][:200]}")
    return f"{c['name']}({json.dumps(c['args'])[:80]})"


@check("Claude Sonnet 4.6 responds")
def c_large():
    r = llm.chat(config.LARGE, [{"role": "user", "content": "Reply with the word OK."}],
                 max_tokens=16)
    if "ok" not in r.text.lower():
        raise RuntimeError(f"unexpected reply: {r.text!r}")
    return f"{r.tokens_in}+{r.tokens_out} tok, ${r.cost:.8f}"


@check("OpenAIRE MCP authenticates and lists tools")
def c_mcp_list():
    tools = MCP().list_tools()
    if not tools:
        raise RuntimeError("tools/list returned nothing")
    names = [t["name"] for t in tools]
    globals()["_TOOL_NAMES"] = names
    return f"{len(names)} tools: {', '.join(names[:4])}..."


@check("OpenAIRE returns real results for a well-formed query")
def c_mcp_call():
    m = MCP()
    out = m.call("search_research_products",
                 {"query": "CRISPR", "page_size": 5, "sort_by": "citationCount DESC"})
    if not out["ok"] or out["n_results"] == 0:
        raise RuntimeError(f"expected results, got {out['n_results']}: {out['text'][:200]}")
    return f"{out['n_results']} results, {len(out['text'])} chars"


@check("PREMISE: an over-specified query returns zero results")
def c_premise():
    m = MCP()
    narrow = ("antibody drug conjugate cleavable linker plasma stability "
              "payload potency off-target toxicity clinical outcomes")
    out = m.call("search_research_products", {"query": narrow, "page_size": 5})
    if out["n_results"] > 0:
        raise RuntimeError(
            f"expected 0 results but got {out['n_results']} — the AND-logic failure "
            f"mode may not reproduce; make the eval questions harder")
    return "0 results as expected — the failure mode we exploit is real"


if __name__ == "__main__":
    print("\nCIRCUIT access check\n" + "=" * 60)
    for fn in (c_key, c_prices, c_small, c_small_tools, c_large,
               c_mcp_list, c_mcp_call, c_premise):
        fn()

    ok = sum(1 for p, _, _ in RESULTS if p)
    print("=" * 60)
    if ok == len(RESULTS):
        print(f"ALL CHECKS PASSED ({ok}/{len(RESULTS)}) — safe to build the harness.\n")
        sys.exit(0)
    print(f"{ok}/{len(RESULTS)} passed. Failures:")
    for p, n, d in RESULTS:
        if not p:
            print(f"  - {n}: {d}")
    print()
    sys.exit(1)
