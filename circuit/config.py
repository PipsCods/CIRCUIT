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


def _read_dotenv() -> dict:
    env = ROOT / ".env"
    if not env.exists():
        return {}
    out = {}
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip("'\"")
    return out


DOTENV = _read_dotenv()


def _cfg(key, default=""):
    """.env wins over the inherited shell.

    Deliberate: a developer shell may already export ANTHROPIC_* for some other
    tool, and silently picking that up would point the harness at the wrong
    account or gateway mid-experiment.
    """
    return DOTENV.get(key) or os.environ.get(key, default)


OPENROUTER_KEY = _cfg("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

ANTHROPIC_KEY = _cfg("ANTHROPIC_API_KEY")
# Only honoured from .env — never inherited, so a stray shell export cannot
# redirect billed traffic to a proxy without us noticing.
ANTHROPIC_BASE_URL = DOTENV.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

SMALL = "google/gemma-4-26b-a4b-it"      # via OpenRouter
LARGE = "claude-sonnet-4-6"              # via the Anthropic SDK
FABLE = "claude-fable-5"                 # via the Anthropic SDK

PROVIDER = {
    SMALL: "openrouter",
    LARGE: "anthropic",
    FABLE: "anthropic",
}

# USD per token. The OpenRouter entries are re-verified against the live models
# endpoint by smoke.py; the Anthropic entries are list pricing and are checked by
# hand. Cache reads/writes are not modelled — we do not use prompt caching.
PRICES = {
    SMALL: {"in": 0.00000012, "out": 0.00000035},
    LARGE: {"in": 0.000003, "out": 0.000015},
    FABLE: {"in": 0.000010, "out": 0.000050},
}

# Fable 5 has always-on adaptive thinking and rejects temperature values other
# than 1.0. Omitting the parameter uses its only supported sampling behavior.
NO_TEMPERATURE = {FABLE}

SEED = 20260725
TEMPERATURE = 0.0
MAX_TOKENS = 2048
MAX_TURNS = 6

MCP_OPENAIRE = "https://openaire.mcp.alien.club/mcp"

# The live server namespaces every tool with an `openaire_` prefix. Alien's
# explore-openaire skill documents them WITHOUT it, so trust this list, not the
# skill doc.
T_SEARCH = "openaire_search_research_products"
T_INFLUENCE = "openaire_find_by_influence_class"
T_DETAILS = "openaire_get_research_product_details"
T_RELATIONS = "openaire_explore_research_relationships"

MCP_BIORXIV = "https://biorxiv.mcp.alien.club/mcp"
MCP_MEDRXIV = "https://medrxiv.mcp.alien.club/mcp"


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    p = PRICES[model]
    return tokens_in * p["in"] + tokens_out * p["out"]
