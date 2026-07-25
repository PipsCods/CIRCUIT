"""Provider-neutral tool-calling loop for the CIRCUIT experiment."""
import json

from . import llm
from .mcp_client import MCP


def _parse_final(text):
    try:
        return json.loads(text), None
    except (json.JSONDecodeError, TypeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def run(model, context, question, max_turns=6):
    """Run one question and return a JSON-serializable execution trace."""
    messages = [
        {"role": "system", "content": context.system_prompt},
        {"role": "user", "content": question},
    ]
    allowed_tools = {
        tool["function"]["name"] for tool in context.tools
    }
    # Construct the retrieval client only if the model actually emits an
    # allowed tool call. A context with no tools is therefore intrinsically
    # model-only: it cannot initialize, authenticate to, or query OpenAIRE.
    mcp = None
    calls = []
    tokens_in = 0
    tokens_out = 0
    cost = 0.0
    final_text = ""
    turns = 0

    for turn_index in range(max_turns):
        reply = llm.chat(model, messages, tools=context.tools)
        turns = turn_index + 1
        tokens_in += reply.tokens_in
        tokens_out += reply.tokens_out
        cost += reply.cost
        final_text = reply.text

        if not reply.tool_calls:
            break

        normalized_calls = []
        for call_index, call in enumerate(reply.tool_calls):
            call_id = call.get("id") or f"call_{turns}_{call_index + 1}"
            args = call.get("args")
            if not isinstance(args, dict):
                args = {"__malformed__": str(args)}
            normalized_calls.append({
                "id": call_id,
                "name": call.get("name") or "",
                "args": args,
            })

        assistant_message = {
            "role": "assistant",
            "content": reply.text,
            "tool_calls": [{
                "id": call["id"],
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call["args"]),
                },
            } for call in normalized_calls],
        }
        if reply.provider_content:
            assistant_message["_provider_content"] = reply.provider_content
        messages.append(assistant_message)

        for call in normalized_calls:
            trace = {
                "turn": turns,
                "name": call["name"],
                "args": call["args"],
                "n_results": 0,
                "cached": False,
                "ok": False,
            }
            if "__malformed__" in call["args"]:
                content = json.dumps({
                    "error": "Tool arguments were not valid JSON.",
                })
                trace["error"] = "malformed arguments"
            elif call["name"] not in allowed_tools:
                content = json.dumps({
                    "error": f"Unknown or unavailable tool: {call['name']}",
                })
                trace["error"] = "unknown tool"
            else:
                try:
                    if mcp is None:
                        mcp = MCP()
                    out = mcp.call(call["name"], call["args"])
                    trace.update({
                        "n_results": out["n_results"],
                        "cached": out["cached"],
                        "ok": out["ok"],
                    })
                    content = out["text"]
                except Exception as exc:
                    trace["error"] = f"{type(exc).__name__}: {exc}"
                    content = json.dumps({"error": trace["error"]})
            calls.append(trace)
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "name": call["name"],
                "content": content,
            })

    parsed, parse_error = _parse_final(final_text)
    if turns == max_turns and reply.tool_calls:
        parsed = None
        parse_error = f"no final response within {max_turns} turns"

    return {
        "tool_calls": calls,
        "final_text": final_text,
        "parsed": parsed,
        "parse_error": parse_error,
        "turns": turns,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_total": tokens_in + tokens_out,
        "cost": cost,
    }
