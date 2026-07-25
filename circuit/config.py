"""Central config: paths, models, price table."""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
SECRETS = ROOT / ".secrets"
RUNS = ROOT / "runs"
DATA = ROOT / "data"

for _d in (CACHE / "mcp", CACHE / "doi", SECRETS, RUNS, DATA):
    _d.mkdir(parents=True, exist_ok=True)


def _load_dotenv():
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


_load_dotenv()

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SMALL = "google/gemma-4-26b-a4b-it"
LARGE = "anthropic/claude-sonnet-4.6"

# USD per token, mirrored from the OpenRouter models endpoint.
# smoke.py re-verifies these against the live API so they cannot silently drift.
PRICES = {
    SMALL: {"in": 0.00000012, "out": 0.00000035},
    LARGE: {"in": 0.000003, "out": 0.000015},
}

SEED = 20260725

MCP_OPENAIRE = "https://openaire.mcp.alien.club/mcp"
MCP_BIORXIV = "https://biorxiv.mcp.alien.club/mcp"
MCP_MEDRXIV = "https://medrxiv.mcp.alien.club/mcp"


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    p = PRICES[model]
    return tokens_in * p["in"] + tokens_out * p["out"]
