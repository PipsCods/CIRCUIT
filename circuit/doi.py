"""Dual-source DOI resolution with a deterministic disk cache."""
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config
from .mcp_client import MCP


DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)
DOI_SHAPE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
_CACHE_LOCK = threading.Lock()
_CROSSREF_SEMAPHORE = threading.BoundedSemaphore(2)


def normalize(doi):
    if not isinstance(doi, str):
        return ""
    return DOI_PREFIX.sub("", doi.strip()).rstrip(".,;").lower()


def _cache_path(doi):
    key = json.dumps(["doi_resolution", doi], sort_keys=True)
    return config.CACHE / "doi" / f"{hashlib.sha256(key.encode()).hexdigest()}.json"


def _openaire_resolves(doi):
    out = MCP().call(config.T_DETAILS, {"identifier": doi})
    if not out["ok"]:
        return False
    try:
        payload = json.loads(out["text"])
    except (json.JSONDecodeError, TypeError):
        return False
    data = payload.get("data") if isinstance(payload, dict) else None
    return (
        bool(payload.get("success"))
        and isinstance(data, dict)
        and normalize(data.get("doi")) == doi
    )


def _crossref_resolves(doi):
    encoded = urllib.parse.quote(doi, safe="")
    req = urllib.request.Request(
        f"https://api.crossref.org/works/{encoded}",
        headers={
            "Accept": "application/json",
            "User-Agent": "CIRCUIT/0.1 (deterministic citation evaluation)",
        },
    )
    for attempt in range(4):
        try:
            with _CROSSREF_SEMAPHORE:
                with urllib.request.urlopen(req, timeout=30) as response:
                    payload = json.loads(response.read())
            break
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 404):
                return False
            if exc.code != 429 or attempt == 3:
                raise
            retry_after = exc.headers.get("Retry-After")
            try:
                delay = float(retry_after)
            except (TypeError, ValueError):
                delay = attempt + 1
            time.sleep(min(max(delay, 0.5), 5.0))
    message = payload.get("message") if isinstance(payload, dict) else None
    return (
        payload.get("status") == "ok"
        and isinstance(message, dict)
        and normalize(message.get("DOI")) == doi
    )


def resolve(raw_doi):
    doi = normalize(raw_doi)
    if not DOI_SHAPE.match(doi):
        return {
            "doi": doi,
            "resolves_openaire": False,
            "resolves_crossref": False,
            "fabricated": True,
            "cached": False,
        }

    path = _cache_path(doi)
    with _CACHE_LOCK:
        if path.exists():
            cached = json.loads(path.read_text())
            cached["cached"] = True
            return cached

    result = {
        "doi": doi,
        "resolves_openaire": _openaire_resolves(doi),
        "resolves_crossref": _crossref_resolves(doi),
    }
    result["fabricated"] = not (
        result["resolves_openaire"] or result["resolves_crossref"]
    )
    with _CACHE_LOCK:
        path.write_text(json.dumps(result, sort_keys=True))
    result["cached"] = False
    return result
