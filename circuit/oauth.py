"""OAuth for the Alien MCP servers.

The hackathon page says these servers need "no token", which means no *manual*
token — the client dynamically registers itself. The server only grants
authorization_code, so a browser is needed exactly once. We request
`offline_access`, save the refresh token, and every run after that is headless.
"""
import base64
import hashlib
import http.server
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from . import config

REDIRECT_PORT = 8765
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
SCOPES = "openid profile email offline_access"


def _origin(mcp_url: str) -> str:
    p = urllib.parse.urlparse(mcp_url)
    return f"{p.scheme}://{p.netloc}"


def _store(mcp_url: str):
    host = urllib.parse.urlparse(mcp_url).netloc.replace(".", "_")
    return config.SECRETS / f"oauth_{host}.json"


def _post_json(url, payload, form=False):
    if form:
        data = urllib.parse.urlencode(payload).encode()
        ctype = "application/x-www-form-urlencoded"
    else:
        data = json.dumps(payload).encode()
        ctype = "application/json"
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": ctype, "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{url} -> {e.code}: {e.read().decode()[:400]}") from None


def metadata(mcp_url: str) -> dict:
    url = _origin(mcp_url) + "/.well-known/oauth-authorization-server"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def login(mcp_url: str) -> dict:
    """Interactive: register a client, run the PKCE dance, save tokens."""
    meta = metadata(mcp_url)
    reg = _post_json(meta["registration_endpoint"], {
        "client_name": "CIRCUIT hackathon harness",
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_post",
        "scope": SCOPES,
    })
    client_id = reg["client_id"]
    client_secret = reg.get("client_secret", "")

    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)

    box = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            box.update({k: v[0] for k, v in q.items()})
            ok = "code" in box and box.get("state") == state
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<h2>CIRCUIT: authorized. Close this tab.</h2>" if ok
                else b"<h2>CIRCUIT: authorization failed.</h2>")
            done.set()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("localhost", REDIRECT_PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    auth_url = meta["authorization_endpoint"] + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": _origin(mcp_url),
    })
    print("\nOpening browser to authorize. If nothing opens, paste this URL:\n")
    print(auth_url + "\n")
    webbrowser.open(auth_url)

    if not done.wait(300):
        srv.shutdown()
        raise RuntimeError("timed out waiting for the OAuth callback")
    srv.shutdown()

    if box.get("state") != state:
        raise RuntimeError("OAuth state mismatch — aborting")
    if "code" not in box:
        raise RuntimeError(f"no authorization code returned: {box}")

    tok = _post_json(meta["token_endpoint"], {
        "grant_type": "authorization_code",
        "code": box["code"],
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": verifier,
        "resource": _origin(mcp_url),
    }, form=True)

    rec = {
        "client_id": client_id,
        "client_secret": client_secret,
        "token_endpoint": meta["token_endpoint"],
        "access_token": tok["access_token"],
        "refresh_token": tok.get("refresh_token", ""),
        "expires_at": time.time() + tok.get("expires_in", 3600) - 60,
    }
    p = _store(mcp_url)
    p.write_text(json.dumps(rec, indent=2))
    p.chmod(0o600)
    return rec


def access_token(mcp_url: str) -> str:
    """Headless. Loads the saved token, refreshing it if near expiry."""
    p = _store(mcp_url)
    if not p.exists():
        raise RuntimeError(
            f"no saved credentials for {_origin(mcp_url)}.\n"
            f"Run:  python3 scripts/auth_openaire.py")
    rec = json.loads(p.read_text())

    if time.time() < rec.get("expires_at", 0):
        return rec["access_token"]
    if not rec.get("refresh_token"):
        raise RuntimeError("access token expired and no refresh token — re-run auth")

    tok = _post_json(rec["token_endpoint"], {
        "grant_type": "refresh_token",
        "refresh_token": rec["refresh_token"],
        "client_id": rec["client_id"],
        "client_secret": rec["client_secret"],
        "resource": _origin(mcp_url),
    }, form=True)
    rec["access_token"] = tok["access_token"]
    rec["refresh_token"] = tok.get("refresh_token", rec["refresh_token"])
    rec["expires_at"] = time.time() + tok.get("expires_in", 3600) - 60
    p.write_text(json.dumps(rec, indent=2))
    return rec["access_token"]
