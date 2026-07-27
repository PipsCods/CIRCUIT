# CIRCUIT — Better Context Makes Small Models Smarter

## A low-cost research assistant powered by Gemma 4 and OpenAIRE

**Track:** Context Engineering for SLMs (by Alien Intelligence)

## 💡 Inspiration

We tested whether Gemma 4 could reliably find influential papers in OpenAIRE, a
large research database. We asked questions such as:

> What are the most influential papers on CRISPR gene editing? Return five
> papers with DOIs and citation counts.

Researchers need trustworthy answers without paying for a large model every
time. Without tools, a small model may invent plausible papers and DOI strings.
Adding OpenAIRE provides evidence, but its raw interface exposes 43 parameters
and behaviour the model must discover by trial and error.

Most importantly, OpenAIRE uses strict “AND” search logic. Every extra keyword
makes a query narrower. A model that treats it like Google may create an
over-specific query, make invalid calls or spend extra tokens recovering.

## Our solution

CIRCUIT changes the context around Gemma 4. It does not fine-tune or replace
the model.

![How CIRCUIT engineers context](demo/context-engineering-flow.png)

*Figure 1 — CIRCUIT transforms a complex research tool into a small,
evidence-only contract.*

### 1. Prune

CIRCUIT reduces OpenAIRE’s 43 parameters to the query, result count, ranking
and detail level.

### 2. Explain

CIRCUIT teaches strict “AND” logic: begin with two or three essential terms and
remove terms when a search is too narrow.

### 3. Sequence

Gemma starts with minimal records and requests details only when a required
field is missing.

### 4. Recover

If fewer than five complete records exist, Gemma shortens the query, retries at
most twice, and then abstains instead of guessing.

### 5. Ground

The final raw JSON may contain only values found in successful OpenAIRE
evidence: five complete citations or an explicit safe abstention.

## 🛠 How we built it

We used **Gemma 4 26B-A4B Instruct**
(`google/gemma-4-26b-a4b-it`) through OpenRouter. Gemma is the decision-maker in
every condition. It reads the question, chooses search terms, calls OpenAIRE
when tools are available, selects papers and creates the final answer.

We did not fine-tune the model. CIRCUIT uses **prompt and context engineering**
plus tool-based retrieval. It is similar to RAG because Gemma answers from
retrieved evidence, but it does not use embeddings or a vector database.
Instead, Gemma calls the live OpenAIRE research graph through Alien
Intelligence’s MCP interface.

The Python harness uses JSON-RPC over HTTP, OpenAIRE OAuth, and disk caching for
tool responses and DOI checks. There is no Transformers, Keras or custom
inference stack. The offline demo uses static HTML, CSS and JavaScript generated
from real traces.

We now compare three versions of the same Gemma 4 model over the same 25 frozen
questions:

1. **Gemma only:** no tools and no external evidence.
2. **Gemma + vanilla Alien MCP:** the real OpenAIRE tool with its complete
   43-parameter schema.
3. **Gemma + Alien MCP + CIRCUIT:** the same evidence source with an engineered
   prompt and a pruned tool contract.

The vanilla condition is a fair baseline. It receives the real tool description
and the same strict output requirements; it is not designed to fail.

## 🚀 The Prototype

The prototype includes the harness, frozen 25-question benchmark, evidence
ledgers, deterministic scoring, and an offline comparison demo.

- **2-minute demo video:** [Insert public demo video URL before submission]
- **GitHub repository:** [github.com/PipsCods/CIRCUIT](https://github.com/PipsCods/CIRCUIT)

## Evaluation

There is no LLM judge. Every metric is calculated directly from the saved
traces.

- **JSON parse:** the response can be decoded as JSON.
- **Strict contract:** the answer follows the complete required structure.
- **Gold recall@5:** returned DOIs overlap the fixed five-DOI reference set.
- **DOI presence:** the expected number of answers contain a DOI.
- **DOI validity:** the DOI resolves through Crossref.
- **Record grounding:** DOI, title and citation count match saved OpenAIRE
  evidence.
- **Empty calls:** the proportion of tool calls that returned no records.
- **Cost:** input and output tokens multiplied by the fixed model price.

## Results

### Gemma 4

| Config | Method | Strict JSON | Gold R@5 | DOI validity | Empty calls | Record grounded | Mean tokens | Total cost | $/verified |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | Naive MCP | 44.0% | 63.2% | 100.0% | 0.0% | 100.0% | 9,035 | $0.029515 | $0.000236 |
| C | **Engineered MCP** | **96.0%** | **68.0%** | **100.0%** | **0.0%** | 99.2% | **4,187** | **$0.015013** | **$0.000121** |
| G | Intrinsic / no tools | 80.0% | 2.4% | 44.0% | N/A | N/A | 693 | $0.004183 | N/A |

### Opus 4.8 intrinsic baseline

| Evaluation | Result |
|---|---:|
| Questions | 25 |
| JSON parse | 100% |
| Strict contract | 96% |
| Gold recall@5 | 28.0% |
| DOI presence | 96.0% |
| DOI validity | 96.7% |
| Zero-result rate | N/A |
| Total cost | $0.325495 |
| Cost per verified citation | N/A |

## What the results mean

### Gemma without evidence is cheap but unreliable

Gemma without tools costs very little, but its gold recall is only 2.4% and
just 44.0% of its DOI strings are valid. It has no evidence channel for proving
its titles or citation counts.

### Tool access creates a large accuracy gain

Vanilla Alien MCP raises recall from 2.4% to 63.2% and DOI validity from 44.0%
to 100%. The evidence works, but the 43-parameter interface still costs 9,035
tokens per question and produces strict JSON only 44.0% of the time.

### CIRCUIT makes that evidence efficient and usable

CIRCUIT raises recall again, from 63.2% to 68.0%, while preserving 100% DOI
validity. Record grounding remains 99.2%.

Compared with vanilla MCP, CIRCUIT:

- improves strict JSON from 44.0% to 96.0%;
- improves recall by 4.8 percentage points;
- reduces mean tokens by 53.7%;
- reduces total cost by 49.1%; and
- makes each verified citation about 1.95 times cheaper.

### Engineered Gemma versus intrinsic Opus

Opus 4.8 without retrieval reaches 28.0% gold recall at a total cost of
$0.325495. Engineered Gemma reaches 68.0% recall at $0.015013. In this
product-level comparison, CIRCUIT delivers 40 percentage points more recall
while costing about 21.7 times less. The difference is the point of the
experiment: useful context and real evidence can matter more than model size
alone.

## 🧩 Challenges we ran into

The hardest part was not calling the model. It was discovering the real
OpenAIRE contract quickly enough to build a fair experiment in one day.

The deployed tool names had an `openaire_` prefix that was missing from the
available documentation. Search responses also placed results inside a nested
envelope. Our first counter looked only at the top level, which could make a
failed or empty response appear successful.

OpenAIRE also behaves differently from Google: strict “AND” logic means adding
terms often produces fewer results. This became CIRCUIT’s central failure mode.

Finally, the raw search tool exposed 43 parameters, OAuth had to work
headlessly after an initial browser login, and the model sometimes wrapped
otherwise correct JSON in Markdown fences. We solved these problems with a
pruned schema, explicit search instructions, cached OAuth and tool responses,
strict output rules, evidence ledgers, and separate measurements for retrieval
quality and raw JSON compliance.

## Reproducibility

The experiment uses a fixed set of 25 questions, temperature zero, a fixed seed
and fixed model pricing. Every OpenAIRE response is saved with its request,
cache key and hash. Each MCP-backed run also includes an evidence ledger,
provider metadata, token usage and DOI checks.

The vanilla and CIRCUIT artifacts record the same model, question-set hash and
source commit. This makes the context definition the main experimental
difference.

## Conclusion

CIRCUIT demonstrates that evidence access and context engineering solve
different problems.

Alien MCP gives Gemma access to real research. CIRCUIT turns that access into a
contract Gemma can follow: fewer decisions, fewer failed calls, grounded
citations and valid structured output.

The result is a small-model research agent that is more accurate than Gemma
alone, more efficient than the same model using the raw tool, and reaches
higher recall than the intrinsic Opus baseline at about 21.7 times lower cost.
