"""Provider-neutral tool-calling loop for the CIRCUIT experiment."""
import hashlib
import json

from . import config, llm
from .evidence import extract_tool_evidence
from .mcp_client import MCP
from .validation import (
    extract_json,
    is_safe_abstention,
    validate_contract,
    validate_schema_instance,
)


def _parse_final(text):
    extraction = extract_json(text)
    if extraction.raw_parseable:
        return extraction.value, None
    return None, extraction.error


def run(model, context, question, max_turns=config.MAX_TURNS):
    """Run one question and return a JSON-serializable execution trace."""
    messages = [
        {"role": "system", "content": context.system_prompt},
        {"role": "user", "content": question},
    ]
    allowed_tools = {
        tool["function"]["name"]: tool["function"].get("parameters", {})
        for tool in context.tools
    }
    # Construct the retrieval client only if the model actually emits an
    # allowed tool call. A context with no tools is therefore intrinsically
    # model-only: it cannot initialize, authenticate to, or query OpenAIRE.
    mcp = None
    calls = []
    evidence_ledger = []
    evidence_blobs = {}
    model_responses = []
    tokens_in = 0
    tokens_out = 0
    cost = 0.0
    final_text = ""
    turns = 0

    for turn_index in range(max_turns):
        reply = llm.chat(
            model,
            messages,
            tools=context.tools,
            temperature=config.TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
        )
        turns = turn_index + 1
        tokens_in += reply.tokens_in
        tokens_out += reply.tokens_out
        cost += reply.cost
        final_text = reply.text
        model_responses.append({
            "turn": turns,
            "requested_model": model,
            "gateway": reply.gateway or config.PROVIDER.get(model, ""),
            "actual_provider": reply.actual_provider,
            "actual_model": reply.actual_model or model,
            "response_id": reply.response_id,
            "transport_attempts": reply.transport_attempts,
            "temperature": (
                None if model in config.NO_TEMPERATURE else config.TEMPERATURE
            ),
            "seed": config.SEED if reply.gateway == "openrouter" else None,
        })

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
            call_index = len(calls) + 1
            trace = {
                "call_index": call_index,
                "turn": turns,
                "name": call["name"],
                "args": call["args"],
                "argument_schema_errors": [],
                "status": "pending",
                "n_results": None,
                "cached": False,
                "ok": False,
            }
            if "__malformed__" in call["args"]:
                content = json.dumps({
                    "error": "Tool arguments were not valid JSON.",
                })
                trace["error"] = "malformed arguments"
                trace["status"] = "malformed_arguments"
            elif call["name"] not in allowed_tools:
                content = json.dumps({
                    "error": f"Unknown or unavailable tool: {call['name']}",
                })
                trace["error"] = "unknown tool"
                trace["status"] = "unknown_tool"
            else:
                trace["argument_schema_errors"] = validate_schema_instance(
                    call["args"], allowed_tools[call["name"]]
                )
                try:
                    if mcp is None:
                        mcp = MCP()
                    out = mcp.call(call["name"], call["args"])
                    trace.update({
                        "n_results": out["n_results"],
                        "cached": out["cached"],
                        "ok": out["ok"],
                        "cache_key": out["cache_key"],
                        "response_sha256": out["response_sha256"],
                    })
                    content = out["text"]
                    if out["ok"]:
                        trace["status"] = (
                            "success_empty"
                            if out["n_results"] == 0
                            else "success_nonempty"
                        )
                        for row in extract_tool_evidence(content):
                            evidence_ledger.append({
                                "call_index": call_index,
                                "turn": turns,
                                "tool_name": call["name"],
                                **row,
                            })
                    else:
                        trace["status"] = (
                            "schema_invalid"
                            if trace["argument_schema_errors"]
                            else "tool_error"
                        )
                        trace["error"] = content[:2000]
                        trace["error_kind"] = out.get("error_kind", "tool_error")
                except Exception as exc:
                    trace["error"] = f"{type(exc).__name__}: {exc}"
                    content = json.dumps({"error": trace["error"]})
                    trace["status"] = "transport_error"

            response_hash = trace.get("response_sha256")
            if not response_hash:
                response_hash = hashlib.sha256(content.encode()).hexdigest()
                trace["response_sha256"] = response_hash
            trace["response_ref"] = f"evidence/{response_hash}.txt"
            evidence_blobs[response_hash] = content
            calls.append(trace)
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "name": call["name"],
                "content": content,
            })

    parsed, parse_error = _parse_final(final_text)
    extraction = extract_json(final_text)
    if turns == max_turns and reply.tool_calls:
        parsed = None
        parse_error = f"no final response within {max_turns} turns"
        extracted = None
        extraction_method = "missing"
        contract_errors = ["response:no_final_response"]
        safe_abstention = False
    else:
        extracted = extraction.value
        extraction_method = extraction.method
        contract_errors = validate_contract(extracted)
        safe_abstention = is_safe_abstention(extracted)

    return {
        "tool_calls": calls,
        "evidence_ledger": evidence_ledger,
        "_evidence_blobs": evidence_blobs,
        "model_responses": model_responses,
        "final_text": final_text,
        "parsed": parsed,
        "parse_error": parse_error,
        "extracted": extracted,
        "extraction_method": extraction_method,
        "contract_errors": contract_errors,
        "safe_abstention": safe_abstention,
        "turns": turns,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_total": tokens_in + tokens_out,
        "cost": cost,
    }
