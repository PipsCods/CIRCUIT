# CIRCUIT commercial product demo

The demo presents CIRCUIT as an optimization control plane for teams operating
MCP-backed agents. It remains a completely static, offline experience: no
credentials, model calls, MCP calls, or network access are required.

The page has five chapters:

1. **Product:** an auto-running seven-stage compiler simulation that shows
   Gemma-facing output being written live, then keeps every illustrative
   artifact available for inspection.
2. **Savings:** an editable, explicitly illustrative company-cost projection
   and the optimized route selected by the compiler above.
3. **Measured proof:** the frozen 25-question OpenAIRE benchmark.
4. **Trace:** the observable q03 workflow, prompt, tool call, evidence, answer,
   and deterministic checks.
5. **Platform:** the compiler, evaluation corpus, versioning, monitoring, and
   continuous failure-repair loop.

`product-data.js` is intentionally separate from `demo-data.js`. Product data is
an illustrative scenario; benchmark data is generated from real experiment
artifacts. The UI labels this distinction everywhere projected and measured
numbers appear together.

The compiler is the primary above-the-fold experience. Its fictional customer
escalation workflow replays automatically, and both replay controls execute the
same deterministic UI sequence. No Slack, Salesforce, Jira, MCP, or model call
is made. Reduced-motion mode completes the sequence immediately while leaving
all seven stage artifacts keyboard accessible.

`workflow.html` is the compact pitch view. It fits the real q03 question,
five-stage replay, selected OpenAIRE evidence, Gemma answer, deterministic
checks, and naive-context contrast into one desktop presentation viewport.
The exact system prompt and raw JSON remain available in modal artifact views.
The main `index.html` embeds this view as its Trace chapter and starts the
replay when the embedded chapter enters the viewport.

The Gemma (G/A/C) and Opus (J) stages are measured over the frozen 25-question
benchmark. The authoritative display values live in
`data/benchmark-scorecard.json`: raw strict JSON, gold recall@5, DOI validity,
empty-call rate, record grounding, token use, and cost. Opus 4.8 is measured
without tools, so it is clearly labeled as an evidence-access contrast—not a
like-for-like MCP model comparison.

`demo-data.js` is the committed, static payload for the submission build. The
browser makes no model or network calls, and the frozen experiment traces are
intentionally excluded from this UI-only delivery. The q03 chapter automatically
replays the recorded events as it enters the viewport; the replay button runs the
same deterministic animation again. It is explicitly labeled as a frozen trace,
not a fresh model or network execution.

Serve the directory:

```bash
python3 -m http.server 4173 --directory demo
```

Then open <http://127.0.0.1:4173/>.

Build the Netlify-ready multi-file export:

```bash
python3 scripts/build_netlify_single.py
```

The export copies the main product page, illustrative scenario, frozen
benchmark payload, and embedded workflow assets into `netlify-upload/`.
