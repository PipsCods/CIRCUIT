#!/usr/bin/env python3
"""One-time browser login for the Alien MCP servers.

Saves a refresh token to .secrets/ so every later run is headless.
Re-run this only if smoke.py reports an auth failure.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from circuit import config, oauth  # noqa: E402

TARGETS = {
    "openaire": config.MCP_OPENAIRE,
    "biorxiv": config.MCP_BIORXIV,
    "medrxiv": config.MCP_MEDRXIV,
}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "openaire"
    if which not in TARGETS:
        sys.exit(f"unknown target {which!r}; pick one of {list(TARGETS)}")
    url = TARGETS[which]
    print(f"Authorizing {which} -> {url}")
    rec = oauth.login(url)
    print(f"\nSaved. refresh_token present: {bool(rec.get('refresh_token'))}")
    print("Now run: python3 scripts/smoke.py")
