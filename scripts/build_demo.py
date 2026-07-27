#!/usr/bin/env python3
"""Build the static CIRCUIT demo payload from real experiment artifacts."""
import argparse
import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from circuit import config, doi  # noqa: E402


def load_questions():
    return {
        question["id"]: question
        for question in (
            json.loads(line)
            for line in (config.DATA / "questions.jsonl").read_text().splitlines()
            if line.strip()
        )
    }


def load_scorecard():
    path = config.DATA / "benchmark-scorecard.json"
    payload = json.loads(path.read_text())
    scorecard = payload.get("configs")
    if not isinstance(scorecard, dict):
        raise ValueError("benchmark scorecard must contain a configs object")
    required = {"A", "C", "G", "J"}
    missing = required - set(scorecard)
    if missing:
        raise ValueError(
            "benchmark scorecard is missing configurations: "
            + ", ".join(sorted(missing))
        )
    return payload


def load_traces(name, runs_root):
    directory = runs_root / name
    return [
        json.loads(path.read_text())
        for path in sorted(directory.glob("q*.json"))
    ]


def load_manifests(runs_root):
    manifests = {}
    for name in ("A", "C"):
        path = runs_root / name / "manifest.json"
        manifest = json.loads(path.read_text())
        if manifest.get("config") != name:
            raise ValueError(f"{path} does not describe configuration {name}")
        manifests[name] = manifest
    return manifests


def returned_dois(parsed):
    if not isinstance(parsed, dict):
        return []
    citations = parsed.get("citations")
    if not isinstance(citations, list):
        return []
    return [
        doi.normalize(citation.get("doi"))
        for citation in citations
        if isinstance(citation, dict) and isinstance(citation.get("doi"), str)
    ]


def aggregate(name, traces, questions):
    tool_calls = [
        call
        for trace in traces
        for call in trace.get("tool_calls", [])
    ]
    checks = [
        check
        for trace in traces
        for check in trace.get("doi_checks", [])
    ]
    verified = sum(
        bool(check.get("resolves_openaire") or check.get("resolves_crossref"))
        for check in checks
    )
    gold_hits = 0
    for trace in traces:
        predicted = set(returned_dois(trace.get("parsed"))[:5])
        gold_hits += len(predicted & set(questions[trace["qid"]]["gold_dois"]))
    cost = sum(float(trace.get("cost", 0)) for trace in traces)
    n = len(traces)
    return {
        "config": name,
        "questions": n,
        "schema_compliance": (
            sum(trace.get("parse_error") is None for trace in traces) / n
            if n else 0
        ),
        "zero_result_rate": (
            sum(call.get("n_results") == 0 for call in tool_calls) / len(tool_calls)
            if tool_calls else 0
        ),
        "gold_recall_at_5": gold_hits / (5 * n) if n else 0,
        "mean_tokens": (
            sum(int(trace.get("tokens_total", 0)) for trace in traces) / n
            if n else 0
        ),
        "total_cost": cost,
        "verified_citations": verified,
        "doi_validity": verified / len(checks) if checks else None,
        "cost_per_verified": cost / verified if verified else None,
    }


def parse_for_display(trace):
    if isinstance(trace.get("parsed"), dict):
        return trace["parsed"]
    text = trace.get("final_text", "").strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[len("```json"):-len("```")].strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def load_tool_result_summaries(trace, run_dir):
    summaries = []
    for call in trace.get("tool_calls", []):
        reference = call.get("response_ref")
        if not reference:
            continue
        path = run_dir / reference
        try:
            response = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        summary = response.get("summary", {})
        summaries.append({
            "call_index": call.get("call_index"),
            "success": response.get("success"),
            "query": summary.get("query"),
            "results_returned": summary.get("results_returned"),
            "total_results": summary.get("total_results"),
            "response_ref": reference,
            "response_sha256": call.get("response_sha256"),
        })
    return summaries


def trace_payload(trace, gold, run_dir):
    display = parse_for_display(trace)
    citations = display.get("citations", []) if display else []
    checks = {
        doi.normalize(check.get("doi")): check
        for check in trace.get("doi_checks", [])
    }
    gold_dois = set(gold["gold_dois"])
    normalized_citations = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        normalized = doi.normalize(citation.get("doi"))
        check = checks.get(normalized, {})
        normalized_citations.append({
            "doi": normalized,
            "title": citation.get("title", ""),
            "citation_count": citation.get("citation_count"),
            "gold_hit": normalized in gold_dois,
            "verified": bool(
                check.get("resolves_openaire") or check.get("resolves_crossref")
            ),
            "verification_available": bool(check),
        })
    return {
        "config": trace["config"],
        "qid": trace["qid"],
        "run_id": trace.get("run_id"),
        "timestamp": trace.get("timestamp"),
        "model": trace["model"],
        "context": trace["context"],
        "reproducibility": trace.get("reproducibility", {}),
        "tool_calls": trace.get("tool_calls", []),
        "tool_result_summaries": load_tool_result_summaries(trace, run_dir),
        "evidence_ledger": trace.get("evidence_ledger", []),
        "model_responses": trace.get("model_responses", []),
        "final_text": trace.get("final_text", ""),
        "parse_error": trace.get("parse_error"),
        # The baseline uses fenced JSON in this frozen run.  Preserve the raw
        # outcome separately, but use the harness-recovered object for the
        # selected example so the demo never pretends its citations are absent.
        "schema_compliant": display is not None,
        "raw_json_compliant": trace.get("parse_error") is None,
        "extraction_method": trace.get("extraction_method"),
        "contract_errors": trace.get("contract_errors", []),
        "safe_abstention": trace.get("safe_abstention", False),
        "turns": trace.get("turns", 0),
        "tokens_in": trace.get("tokens_in", 0),
        "tokens_out": trace.get("tokens_out", 0),
        "tokens_total": trace.get("tokens_total", 0),
        "cost": trace.get("cost", 0),
        "doi_checks": trace.get("doi_checks", []),
        "resolution_errors": trace.get("resolution_errors", []),
        "citations": normalized_citations,
    }


def context_payload(manifests):
    def frozen_context(name):
        manifest = manifests[name]
        schemas = manifest["tools"]["schemas"]
        search = next(
            tool for tool in schemas
            if tool["function"]["name"] == config.T_SEARCH
        )
        properties = search["function"]["parameters"].get("properties", {})
        return {
            "prompt": manifest["context"]["system_prompt"],
            "prompt_sha256": manifest["context"]["system_prompt_sha256"],
            "tool_count": len(schemas),
            "tool_schema_sha256": manifest["tools"]["sha256"],
            "search_parameter_count": len(properties),
            "search_parameters": list(properties),
            "search_description": search["function"]["description"],
        }

    naive = frozen_context("A")
    engineered = frozen_context("C")
    before = naive["search_parameter_count"]
    after = engineered["search_parameter_count"]
    return {
        "naive": naive,
        "engineered": engineered,
        "transformations": [
            {
                "id": "prune",
                "label": "Prune",
                "summary": f"{before} → {after} search parameters",
                "detail": (
                    "Expose only query, page size, ranking, and detail level—the "
                    "four fields used by this frozen run."
                ),
            },
            {
                "id": "annotate",
                "label": "Annotate",
                "summary": "Teach OpenAIRE AND semantics",
                "detail": (
                    "Start with 2–3 essential terms. More terms narrow results; "
                    "shorten a zero-result query instead of adding synonyms."
                ),
            },
            {
                "id": "sequence",
                "label": "Sequence",
                "summary": "Use minimal evidence directly",
                "detail": (
                    "Minimal records already carry DOI, title, and citation "
                    "count. Request standard detail only if a field is missing."
                ),
            },
            {
                "id": "guard",
                "label": "Guard",
                "summary": "Retry twice, then abstain",
                "detail": (
                    "A failed or empty query is shortened at most twice. If "
                    "evidence remains insufficient, return no citations."
                ),
            },
            {
                "id": "verify",
                "label": "Verify",
                "summary": "Only emit observed DOIs",
                "detail": (
                    "The final answer may cite only DOI values seen in an Alien "
                    "tool result, using one raw JSON object with no Markdown."
                ),
            },
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qid", default="q03")
    parser.add_argument(
        "--runs-root",
        type=pathlib.Path,
        default=config.ROOT / "gemma+mcp_gemma+circuit+mcp",
        help=(
            "frozen MCP experiment directory to visualise "
            "(default: gemma+mcp_gemma+circuit+mcp)"
        ),
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=config.ROOT / "demo" / "demo-data.js",
    )
    args = parser.parse_args()

    questions = load_questions()
    if args.qid not in questions:
        parser.error(f"unknown qid: {args.qid}")

    runs_root = args.runs_root.resolve()
    traces = {name: load_traces(name, runs_root) for name in ("A", "C")}
    manifests = load_manifests(runs_root)
    scorecard = load_scorecard()
    for name in ("A", "C"):
        if len(traces[name]) != 25:
            parser.error(
                f"configuration {name} has {len(traces[name])} traces; expected 25"
            )

    selected = {}
    for name in ("A", "C"):
        try:
            selected[name] = next(
                trace for trace in traces[name]
                if trace["qid"] == args.qid
            )
        except StopIteration:
            parser.error(f"configuration {name} has no {args.qid} trace")

    question = questions[args.qid]
    payload = {
        "source": {
            "question_id": args.qid,
            "question_count": 25,
            "note": (
                "Generated from frozen run manifests and traces, "
                "data/benchmark-scorecard.json, and data/questions.jsonl. "
                "Values are experimental artifacts, not UI fixtures."
            ),
        },
        "question": {
            "id": question["id"],
            "topic": question["topic"],
            "text": selected["A"]["question"],
            "gold_dois": question["gold_dois"],
        },
        "contexts": context_payload(manifests),
        "runs": {
            name: trace_payload(selected[name], question, runs_root / name)
            for name in ("A", "C")
        },
        "aggregate": scorecard["configs"],
    }

    # Refuse to publish a misleading comparison.
    if not payload["runs"]["A"]["schema_compliant"]:
        parser.error("selected naive trace is not schema compliant")
    if not payload["runs"]["C"]["schema_compliant"]:
        parser.error("selected engineered trace is not schema compliant")
    if payload["aggregate"]["C"]["cost_per_verified"] is None:
        parser.error("engineered benchmark has no verified citations")
    if payload["aggregate"]["C"]["mean_tokens"] >= payload["aggregate"]["A"]["mean_tokens"]:
        parser.error("engineered context does not reduce token use")
    if math.isclose(
        payload["contexts"]["naive"]["search_parameter_count"],
        payload["contexts"]["engineered"]["search_parameter_count"],
    ):
        parser.error("context schemas are not meaningfully different")
    for name in ("A", "C"):
        trace_provenance = selected[name].get("reproducibility", {})
        manifest = manifests[name]
        if (
            trace_provenance.get("system_prompt_sha256")
            != manifest["context"]["system_prompt_sha256"]
        ):
            parser.error(f"{name} trace and manifest system prompts do not match")
        if (
            trace_provenance.get("tool_schema_sha256")
            != manifest["tools"]["sha256"]
        ):
            parser.error(f"{name} trace and manifest tool schemas do not match")

    engineered_trace = payload["runs"]["C"]
    ledger_records = {
        (
            doi.normalize(row.get("doi")),
            row.get("title"),
            row.get("citation_count"),
        )
        for row in engineered_trace["evidence_ledger"]
    }
    ungrounded = [
        citation
        for citation in engineered_trace["citations"]
        if (
            citation["doi"],
            citation["title"],
            citation["citation_count"],
        )
        not in ledger_records
    ]
    if ungrounded:
        parser.error("selected engineered answer contains records absent from evidence")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    args.output.write_text(
        "window.CIRCUIT_DEMO_DATA = " + serialized + ";\n"
    )
    print(
        f"Wrote {args.output.relative_to(config.ROOT)} "
        f"from {len(traces['A']) + len(traces['C'])} traces"
    )


if __name__ == "__main__":
    main()
