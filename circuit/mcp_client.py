"""Minimal MCP client (JSON-RPC over streamable HTTP) with a disk cache.

Every tools/call result is cached on disk keyed by (server, tool, args). This
buys three things at once: reruns are instant, reruns are byte-identical, and
the demo still works with no network.
"""
import hashlib
import json
import urllib.error
import urllib.request

from . import config, oauth


def _sse_or_json(body: bytes) -> dict:
    """Streamable HTTP may answer as JSON or as an SSE stream."""
    text = body.decode("utf-8", "replace").strip()
    if not text:
        return {}
    if text.startswith("{"):
        return json.loads(text)
    for line in text.splitlines():
        if line.startswith("data:"):
            chunk = line[5:].strip()
            if chunk and chunk != "[DONE]":
                return json.loads(chunk)
    raise RuntimeError(f"unparseable MCP response: {text[:300]}")


class MCP:
    def __init__(self, url=config.MCP_OPENAIRE, use_cache=True):
        self.url = url
        self.use_cache = use_cache
        self.session = None
        self._id = 0
        self._ready = False

    def _rpc(self, method, params=None, notify=False):
        self._id += 1
        payload = {"jsonrpc": "2.0", "method": method}
        if not notify:
            payload["id"] = self._id
        if params is not None:
            payload["params"] = params

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {oauth.access_token(self.url)}",
            "MCP-Protocol-Version": "2025-06-18",
        }
        if self.session:
            headers["Mcp-Session-Id"] = self.session

        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                sid = r.headers.get("Mcp-Session-Id")
                if sid:
                    self.session = sid
                if notify:
                    return {}
                return _sse_or_json(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"MCP {method} -> {e.code}: {e.read().decode()[:300]}") from None

    def connect(self):
        if self._ready:
            return self
        r = self._rpc("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "circuit", "version": "0.1"},
        })
        if "error" in r:
            raise RuntimeError(f"initialize failed: {r['error']}")
        self._rpc("notifications/initialized", notify=True)
        self._ready = True
        return self

    def list_tools(self) -> list:
        self.connect()
        r = self._rpc("tools/list")
        if "error" in r:
            raise RuntimeError(f"tools/list failed: {r['error']}")
        return r.get("result", {}).get("tools", [])

    def _cache_path(self, tool, args):
        key = json.dumps([self.url, tool, args], sort_keys=True)
        return config.CACHE / "mcp" / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    @staticmethod
    def _decorate(out, path, cached):
        result = dict(out)
        if not result.get("ok"):
            # A failed call has no result cardinality. Keeping this distinct
            # prevents failures from being counted as successful empty searches.
            result["n_results"] = None
            result.setdefault("error_kind", "tool_error")
        text = result.get("text")
        if not isinstance(text, str):
            text = str(text or "")
            result["text"] = text
        result["response_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        result["cache_key"] = path.stem
        result["cached"] = cached
        return result

    def call(self, tool: str, args: dict) -> dict:
        """Call a tool with explicit success/error cardinality and provenance."""
        path = self._cache_path(tool, args)
        if self.use_cache and path.exists():
            out = json.loads(path.read_text())
            return self._decorate(out, path, True)

        self.connect()
        r = self._rpc("tools/call", {"name": tool, "arguments": args})
        if "error" in r:
            out = {
                "ok": False,
                "text": json.dumps(r["error"])[:2000],
                "n_results": None,
                "error_kind": "mcp_error",
            }
        else:
            res = r.get("result", {})
            text = "\n".join(
                c.get("text", "") for c in res.get("content", [])
                if c.get("type") == "text")
            ok = not res.get("isError", False)
            out = {
                "ok": ok,
                "text": text,
                "n_results": _count_results(text) if ok else None,
            }
            if not ok:
                out["error_kind"] = "tool_error"

        path.write_text(json.dumps(out))
        return self._decorate(out, path, False)


def _count_results(text: str) -> int:
    """Result count for an Alien MCP payload.

    Responses use the envelope {success, data:{results,pagination}, summary,
    _debug}. `summary.results_returned` is authoritative when present; the
    nested scan is the fallback for tools that shape their output differently.
    """
    if not text.strip():
        return 0
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        return 1
    if isinstance(d, list):
        return len(d)
    if not isinstance(d, dict):
        return 1

    summary = d.get("summary")
    if isinstance(summary, dict) and isinstance(summary.get("results_returned"), int):
        return summary["results_returned"]

    for scope in (d.get("data"), d):
        if not isinstance(scope, dict):
            continue
        for k in ("results", "datasets", "products", "items", "authors", "nodes"):
            if isinstance(scope.get(k), list):
                return len(scope[k])
    return 1
