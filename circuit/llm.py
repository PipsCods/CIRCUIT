"""Unified chat interface over OpenRouter and Anthropic.

Gemma 4 goes through OpenRouter; Claude Sonnet 4.6 and Claude Fable 5 go through
the Anthropic SDK. Messages and tools are written once in OpenAI shape (the
canonical form for this harness) and translated for Anthropic here, so the
runner never branches on provider.

Caveat we state openly in the writeup: the Anthropic API has no `seed`
parameter, so Sonnet's determinism rests on temperature=0 alone, while Gemma is
both seeded and temperature-0. Sonnet is the *baseline* being compared against,
not the subject of the intervention, so this does not affect the claim — but it
does mean Sonnet's numbers can move slightly between runs. Fable 5 additionally
does not support temperature=0, so the parameter is omitted for that optional
model.
"""
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from . import config


@dataclass
class Reply:
    text: str
    tool_calls: list = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    raw: dict = field(default_factory=dict)
    # Provider-native assistant content to carry unchanged into a follow-up
    # turn. Fable 5 requires its adaptive-thinking blocks to be preserved.
    provider_content: list = field(default_factory=list)
    gateway: str = ""
    actual_provider: str = ""
    actual_model: str = ""
    response_id: str = ""


def chat(model, messages, tools=None, temperature=0.0, max_tokens=2048,
         response_format=None, timeout=120):
    """One chat completion against either provider.

    tool_calls come back as [{"id","name","args"(dict)}]. Malformed tool
    arguments are surfaced under args["__malformed__"] rather than raising — a
    small model emitting bad JSON is a result we want to measure, not an
    exception that aborts the run.
    """
    provider = config.PROVIDER.get(model, "openrouter")
    if provider == "anthropic":
        return _anthropic(model, messages, tools, temperature, max_tokens, timeout)
    return _openrouter(model, messages, tools, temperature, max_tokens,
                       response_format, timeout)


# --------------------------------------------------------------------------- #
# OpenRouter (Gemma 4)
# --------------------------------------------------------------------------- #

def _openrouter(model, messages, tools, temperature, max_tokens,
                response_format, timeout):
    if not config.OPENROUTER_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set (put it in .env)")

    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "seed": config.SEED,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if response_format:
        body["response_format"] = response_format

    req = urllib.request.Request(
        config.OPENROUTER_URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {config.OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "X-Title": "CIRCUIT",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenRouter {e.code}: {e.read().decode()[:400]}") from None

    if "choices" not in data:
        raise RuntimeError(f"OpenRouter returned no choices: {str(data)[:400]}")

    msg = data["choices"][0]["message"]
    calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        calls.append({
            "id": tc.get("id"),
            "name": fn.get("name"),
            "args": _parse_args(fn.get("arguments") or "{}"),
        })

    usage = data.get("usage") or {}
    ti, to = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    return Reply(
        text=msg.get("content") or "",
        tool_calls=calls,
        tokens_in=ti,
        tokens_out=to,
        cost=config.cost_usd(model, ti, to),
        raw=data,
        gateway="openrouter",
        actual_provider=data.get("provider") or "openrouter-unspecified",
        actual_model=data.get("model") or model,
        response_id=data.get("id") or "",
    )


def _parse_args(raw):
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"__malformed__": str(raw)}


# --------------------------------------------------------------------------- #
# Anthropic (Claude Sonnet 4.6 and Claude Fable 5)
# --------------------------------------------------------------------------- #

_client = None


def _anthropic_client():
    global _client
    if _client is None:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError(
                "anthropic SDK missing — run:  .venv/bin/pip install anthropic\n"
                "and invoke scripts with .venv/bin/python") from None
        if not config.ANTHROPIC_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set (put it in .env)")
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_KEY,
                                      base_url=config.ANTHROPIC_BASE_URL)
    return _client


def _to_anthropic(messages, tools):
    """Translate OpenAI-shaped messages/tools into Anthropic shape."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")

    out = []
    for m in messages:
        role = m["role"]
        if role == "system":
            continue

        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": m.get("tool_call_id"),
                "content": m.get("content") or "",
            }
            # Anthropic requires tool results to be user-role blocks, and
            # consecutive results must share one message.
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue

        if role == "assistant" and m.get("tool_calls"):
            # Fable 5 requires thinking blocks to be passed back unchanged.
            # Prefer the original Anthropic content when the preceding reply
            # supplied it; reconstructed OpenAI-shaped blocks remain the
            # fallback for Sonnet and caller-authored histories.
            if m.get("_provider_content"):
                out.append({"role": "assistant", "content": m["_provider_content"]})
                continue

            blocks = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                fn = tc.get("function", tc)
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id"),
                    "name": fn.get("name"),
                    "input": _parse_args(fn.get("arguments", fn.get("args", {}))),
                })
            out.append({"role": "assistant", "content": blocks})
            continue

        out.append({"role": role, "content": m.get("content") or ""})

    a_tools = [{
        "name": t["function"]["name"],
        "description": t["function"].get("description", ""),
        "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}}),
    } for t in (tools or [])]

    return system, out, a_tools


def _anthropic(model, messages, tools, temperature, max_tokens, timeout):
    client = _anthropic_client()
    system, msgs, a_tools = _to_anthropic(messages, tools)

    kwargs = {
        "model": model,
        "messages": msgs,
        "max_tokens": max_tokens,
        "timeout": timeout,
    }
    if model not in config.NO_TEMPERATURE:
        kwargs["temperature"] = temperature
    if system:
        kwargs["system"] = system
    if a_tools:
        kwargs["tools"] = a_tools

    try:
        resp = client.messages.create(**kwargs)
    except Exception as e:
        raise RuntimeError(f"Anthropic API: {type(e).__name__}: {str(e)[:400]}") from None

    if resp.stop_reason == "refusal":
        details = getattr(resp, "stop_details", None)
        if hasattr(details, "model_dump"):
            details = details.model_dump()
        raise RuntimeError(f"Anthropic refusal: {details or 'no details returned'}")

    text_parts, calls = [], []
    for block in resp.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            calls.append({"id": block.id, "name": block.name,
                          "args": block.input if isinstance(block.input, dict) else {}})

    ti, to = resp.usage.input_tokens, resp.usage.output_tokens
    provider_content = [
        block.model_dump() if hasattr(block, "model_dump") else block
        for block in resp.content
    ]
    raw = resp.model_dump()
    return Reply(
        text="".join(text_parts),
        tool_calls=calls,
        tokens_in=ti,
        tokens_out=to,
        cost=config.cost_usd(model, ti, to),
        raw=raw,
        provider_content=provider_content,
        gateway="anthropic",
        actual_provider="anthropic",
        actual_model=raw.get("model") or model,
        response_id=raw.get("id") or "",
    )
