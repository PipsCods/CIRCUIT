# CIRCUIT demo

The demo is a short, scroll-led explanation built from the frozen experiment
artifacts. It makes no network or model calls in the browser.

The page has three beats:

1. The measured benefit of CIRCUIT, visible immediately.
2. The progression from Gemma alone, to Vanilla Alien MCP, to Alien MCP with
   engineered context.
3. The measured evidence-access contrast: Gemma + CIRCUIT versus intrinsic
   Opus 4.8.

The Gemma (G/A/C) and Opus (J) stages are measured over the frozen 25-question
benchmark. The authoritative display values live in
`data/benchmark-scorecard.json`: raw strict JSON, gold recall@5, DOI validity,
empty-call rate, record grounding, token use, and cost. Opus 4.8 is measured
without tools, so it is clearly labeled as an evidence-access contrast—not a
like-for-like MCP model comparison.

`demo-data.js` is the committed, static payload for the submission build. The
browser makes no model or network calls, and the frozen experiment traces are
intentionally excluded from this UI-only delivery.

Serve the directory:

```bash
python3 -m http.server 4173 --directory demo
```

Then open <http://127.0.0.1:4173/>.
