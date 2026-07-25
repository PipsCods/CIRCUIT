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


@check("ANTHROPIC_API_KEY is set")
def c_key_anthropic():
    if not config.ANTHROPIC_KEY:
        raise RuntimeError("missing — add ANTHROPIC_API_KEY to .env")
    if config.ANTHROPIC_BASE_URL != "https://api.anthropic.com":
        return f"...{config.ANTHROPIC_KEY[-6:]}  (base_url={config.ANTHROPIC_BASE_URL})"
    return f"...{config.ANTHROPIC_KEY[-6:]}"


@check("price table matches live OpenRouter pricing")
def c_prices():
    with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=60) as r:
        live = {m["id"]: m.get("pricing", {}) for m in json.load(r)["data"]}
    drift, checked = [], 0
    for model, p in config.PRICES.items():
        # Only OpenRouter-served models can be verified here. The Anthropic
        # entry is list pricing and is maintained by hand.
        if config.PROVIDER.get(model) != "openrouter":
            continue
        if model not in live:
            raise RuntimeError(f"{model} not offered by OpenRouter any more")
        checked += 1
        for ours, theirs in (("in", "prompt"), ("out", "completion")):
            got = float(live[model][theirs])
            if abs(got - p[ours]) > 1e-12:
                drift.append(f"{model}.{ours}: ours={p[ours]} live={got}")
    if drift:
        raise RuntimeError("update config.PRICES — " + "; ".join(drift))
    return f"{checked} verified live, 1 manual (anthropic)"


@check("Gemma 4 responds")
def c_small():
    r = llm.chat(config.SMALL, [{"role": "user", "content": "Reply with the word OK."}],
                 max_tokens=16)
    if "ok" not in r.text.lower():
        raise RuntimeError(f"unexpected reply: {r.text!r}")
    return f"{r.tokens_in}+{r.tokens_out} tok, ${r.cost:.8f}"


DEMO_TOOL = [{
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
TOOL_PROMPT = [{"role": "user",
                "content": "Find papers about CRISPR gene editing. Use the tool."}]


def _assert_tool_call(r):
    if not r.tool_calls:
        raise RuntimeError("no tool_calls returned — the harness would need to fall "
                           "back to prompt-emitted JSON tool specs")
    c = r.tool_calls[0]
    if "__malformed__" in c["args"]:
        raise RuntimeError(f"malformed tool arguments: {c['args']['__malformed__'][:200]}")
    return f"{c['name']}({json.dumps(c['args'])[:70]})"


@check("Gemma 4 emits a well-formed tool call")
def c_small_tools():
    return _assert_tool_call(
        llm.chat(config.SMALL, TOOL_PROMPT, tools=DEMO_TOOL, max_tokens=256))


@check("Claude Sonnet 4.6 responds via the Anthropic SDK")
def c_large():
    r = llm.chat(config.LARGE, [{"role": "user", "content": "Reply with the word OK."}],
                 max_tokens=16)
    if "ok" not in r.text.lower():
        raise RuntimeError(f"unexpected reply: {r.text!r}")
    return f"{r.tokens_in}+{r.tokens_out} tok, ${r.cost:.8f}"


@check("Sonnet tool translation round-trips (OpenAI shape -> Anthropic)")
def c_large_tools():
    r = llm.chat(config.LARGE, TOOL_PROMPT, tools=DEMO_TOOL, max_tokens=256)
    return _assert_tool_call(r)


@check("Sonnet accepts a tool_result turn (multi-turn translation)")
def c_large_roundtrip():
    """The runner feeds tool output back for another turn. Anthropic needs
    tool_use/tool_result pairing that OpenAI does not, so exercise it now
    rather than discovering the shape mismatch mid-experiment."""
    first = llm.chat(config.LARGE, TOOL_PROMPT, tools=DEMO_TOOL, max_tokens=256)
    if not first.tool_calls:
        raise RuntimeError("no tool call to respond to")
    call = first.tool_calls[0]
    convo = TOOL_PROMPT + [
        {"role": "assistant", "content": first.text,
         "tool_calls": [{"id": call["id"], "type": "function",
                         "function": {"name": call["name"],
                                      "arguments": json.dumps(call["args"])}}]},
        {"role": "tool", "tool_call_id": call["id"],
         "content": json.dumps({"results": [
             {"title": "A programmable dual-RNA-guided DNA endonuclease",
              "doi": "10.1126/science.1225829", "citation_count": 12000}]})},
    ]
    second = llm.chat(config.LARGE, convo, tools=DEMO_TOOL, max_tokens=256)
    if "1225829" not in second.text and "endonuclease" not in second.text.lower():
        raise RuntimeError(f"tool result not reflected in reply: {second.text[:160]!r}")
    return f"grounded reply, {second.tokens_in}+{second.tokens_out} tok"


@check("OpenAIRE MCP authenticates and exposes the tools we depend on")
def c_mcp_list():
    names = {t["name"] for t in MCP().list_tools()}
    if not names:
        raise RuntimeError("tools/list returned nothing")
    need = {config.T_SEARCH, config.T_INFLUENCE, config.T_DETAILS, config.T_RELATIONS}
    missing = need - names
    if missing:
        raise RuntimeError(f"expected tools absent: {sorted(missing)}")
    return f"{len(names)} tools, all 4 required present"


@check("OpenAIRE returns real results for a well-formed query")
def c_mcp_call():
    out = MCP().call(config.T_SEARCH, {"query": "CRISPR", "page_size": 5})
    if not out["ok"]:
        raise RuntimeError(f"call failed: {out['text'][:250]}")
    if out["n_results"] == 0:
        raise RuntimeError("well-formed query returned nothing — check param names")
    return f"{out['n_results']} results, {len(out['text'])} chars"


@check("PREMISE: an over-specified query returns zero results")
def c_premise():
    narrow = ("antibody drug conjugate cleavable linker plasma stability "
              "payload potency off-target toxicity clinical outcomes")
    out = MCP().call(config.T_SEARCH, {"query": narrow, "page_size": 5})
    # Must distinguish "the query legitimately matched nothing" from "the call
    # errored". Only the former validates the premise.
    if not out["ok"]:
        raise RuntimeError(f"call errored, premise untested: {out['text'][:250]}")
    if out["n_results"] > 0:
        raise RuntimeError(
            f"expected 0 results but got {out['n_results']} — the AND-logic failure "
            f"mode may not reproduce; make the eval questions harder")
    return "0 results as expected — the failure mode we exploit is real"


if __name__ == "__main__":
    print("\nCIRCUIT access check\n" + "=" * 60)
    for fn in (c_key, c_key_anthropic, c_prices, c_small, c_small_tools,
               c_large, c_large_tools, c_large_roundtrip,
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
