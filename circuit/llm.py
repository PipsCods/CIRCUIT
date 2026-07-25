"""OpenRouter chat client. Both models go through here so the API surface is
identical between configs — that removes a confound from the comparison."""
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


def chat(model, messages, tools=None, temperature=0.0, max_tokens=2048,
         response_format=None, timeout=120):
    """One chat completion. Returns a Reply.

    tool_calls come back as [{"id","name","args"(dict)}]. Malformed tool
    arguments are surfaced as a raw string under "args_raw" rather than
    raising — a small model emitting bad JSON is a result we want to measure,
    not an exception that aborts the run.
    """
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
        raw_args = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            args = {"__malformed__": raw_args}
        calls.append({"id": tc.get("id"), "name": fn.get("name"), "args": args})

    usage = data.get("usage") or {}
    ti = usage.get("prompt_tokens", 0)
    to = usage.get("completion_tokens", 0)
    return Reply(
        text=msg.get("content") or "",
        tool_calls=calls,
        tokens_in=ti,
        tokens_out=to,
        cost=config.cost_usd(model, ti, to),
        raw=data,
    )
