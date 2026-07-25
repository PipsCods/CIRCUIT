# CIRCUIT

Context engineering for small language models. Hackathon build (Alien Intelligence / Gemma 4, 5 hours).

## The claim we are proving

**Gemma 4 with engineered context matches or beats a frontier model with naive context, at a fraction of the cost.**

Measured deterministically. No LLM judge anywhere.

## The task

Evidence-grounded citation retrieval over the OpenAIRE research graph. One prompt template, ~25 instances:

> "What are the most influential papers on `<TOPIC>`? Return N with DOIs and citation counts."

Output contract is strict JSON:

```json
{"answer": "...", "citations": [{"doi": "...", "title": "...", "citation_count": 0}]}
```

The failure mode we target: a naive small model malforms its OpenAIRE query, gets zero
results, and then fabricates plausible papers from parametric memory. A DOI either
resolves or it does not — so the hallucination rate is a string lookup, not a rubric.

## Experiment matrix

|                    | Naive context | Engineered context |
| ------------------ | ------------- | ------------------ |
| Gemma 4 (26B-A4B)  | **A** floor   | **C** our product  |
| Claude Sonnet 4.6  | **B** the bar | **D** headroom     |

Target result: **C >= B on accuracy, at far below B's cost.** D shows the technique is
not overfit to Gemma.

Config A/B must be a *fair* naive baseline — real out-of-the-box MCP tool descriptions
plus a sensible one-paragraph prompt. Not a strawman. We say this out loud in the pitch.

## Metrics

All deterministic, all computed by `circuit/score.py`.

| Metric                     | Definition                                    |
| -------------------------- | --------------------------------------------- |
| DOI validity rate          | fraction of returned DOIs that resolve        |
| Gold recall@5              | set overlap with pre-built gold DOIs          |
| Zero-result call rate      | MCP calls returning no results                |
| Schema compliance          | `json.loads()` on the model output succeeds   |
| Cost (USD)                 | tokens x price table                          |
| **Cost per verified cite** | the headline number                           |

## Determinism rules

These are non-negotiable — the whole pitch rests on reproducibility.

- `temperature=0`, fixed `seed`, fixed question order.
- **Every MCP call is disk-cached** keyed on `sha256(tool + sorted args)`. Reruns are
  instant, identical, and work with no network. The demo survives venue wifi dying.
- Every DOI resolution is disk-cached the same way.
- Both models are called through **the same OpenRouter client** with the same params.
  Uniform API surface removes a confound and gives one consistent price table.

## Layout

```
circuit/
  config.py       models, price table, paths
  llm.py          OpenRouter chat client -> (text, tool_calls, usage, cost)
  oauth.py        OpenAIRE OAuth: token load / refresh
  mcp_client.py   MCP JSON-RPC over streamable HTTP, disk-cached
scripts/
  auth_openaire.py  one-time browser login, saves refresh token
  smoke.py          the access check — run this first
.cache/           MCP + DOI caches (gitignored, safe to delete)
.secrets/         OAuth tokens (gitignored, NEVER commit)
```

## Setup

```bash
cp .env.example .env      # add OPENROUTER_API_KEY
python3 scripts/auth_openaire.py    # one-time, opens browser
python3 scripts/smoke.py            # must print ALL CHECKS PASSED
```

## Gotchas that cost us time — do not rediscover these

- **Live tool names are prefixed `openaire_`.** Alien's `explore-openaire` skill doc
  documents them *without* the prefix (`search_research_products`). The doc is wrong for
  this deployment — trust `tools/list`, and use the `T_*` constants in `config.py`.
- **Responses use an envelope**: `{success, data:{results,pagination}, summary, _debug}`.
  Results are at `data.results`, not top level, and `summary.results_returned` /
  `summary.total_results` are authoritative. A counter that scans only the top level
  silently reports 1 for everything, which quietly destroys the zero-result metric.
- **OpenAIRE search is AND logic.** More query terms means *fewer* results, the opposite
  of Google. Verified: `"CRISPR"` returns 5 of 136,389 matches; the same query plus nine
  more terms returns **0 of 0**. This is the single biggest source of naive-model failure
  and the core thing our context fixes.
- **`openaire_search_research_products` takes 43 parameters.** Handing that schema
  verbatim to a 4B-active model is itself a context-engineering failure. Pruning it to
  the ~5 that matter is one of our cheapest, highest-leverage wins.
- `explore_research_relationships` needs **`target_pid`**, not `doi`, for incoming
  citations. The `doi` param finds outgoing refs, which are sparsely indexed.
- `search_datasets` returns `datasets[]`, not `results[]`.
- `get_author_profile` wants `author_name=`, not `orcid=` (ORCID coverage is sparse).
- FOS codes need the **full label**: `"03 medical and health sciences"`, not
  `"medical and health sciences"`.
- Influence classes: C1 top 0.01% (often 0 results for niche topics), C2 top 0.1%,
  **C3 top 1% is the right default**, C4 top 10%, C5 rest.
- The Alien MCPs say "no token" but they mean **OAuth with auto-registration**, not
  anonymous. Headless needs the `offline_access` refresh-token flow in `oauth.py`.

## Conventions

- Stdlib only. No pip installs — zero setup friction matters more than ergonomics today.
- Never commit `.secrets/`.
- Freeze all numbers at the 3h45m mark regardless of how they look. A working demo with
  mediocre numbers beats a broken demo with great ones.
