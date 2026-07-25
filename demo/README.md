# CIRCUIT demo

The demo is a short, scroll-led explanation built from the frozen experiment
artifacts. It makes no network or model calls in the browser.

The page has three beats:

1. The measured benefit of CIRCUIT, visible immediately.
2. The progression from Gemma alone, to raw Alien MCP, to Alien MCP with
   engineered context.
3. The upcoming Gemma + CIRCUIT versus Fable 5 benchmark.

Only the raw-MCP and engineered-context stages have measured values today. The
source is the corrected `runs 2` A/C experiment: both conditions now meet the
strict JSON contract. Gemma without MCP is labeled as a conceptual reference,
and Fable 5 is labeled as not yet run.

Generate `demo-data.js` from the frozen A/C runs and real context definitions:

```bash
.venv/bin/python scripts/build_demo.py
```

Serve the directory:

```bash
python3 -m http.server 4173 --directory demo
```

Then open <http://127.0.0.1:4173/>.
