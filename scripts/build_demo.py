#!/usr/bin/env python3
"""Build the static CIRCUIT demo payload from real experiment artifacts."""
import argparse
import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from circuit import config, contexts, doi  # noqa: E402


def load_questions():
    return {
        question["id"]: question
        for question in (
            json.loads(line)
            for line in (config.DATA / "questions.jsonl").read_text().splitlines()
            if line.strip()
        )
    }


def load_traces(name, runs_root):
    directory = runs_root / name
    return [
        json.loads(path.read_text())
        for path in sorted(directory.glob("q*.json"))
    ]


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


def trace_payload(trace, gold):
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
        "model": trace["model"],
        "context": trace["context"],
        "tool_calls": trace.get("tool_calls", []),
        "final_text": trace.get("final_text", ""),
        "parse_error": trace.get("parse_error"),
        "schema_compliant": trace.get("parse_error") is None,
        "turns": trace.get("turns", 0),
        "tokens_in": trace.get("tokens_in", 0),
        "tokens_out": trace.get("tokens_out", 0),
        "tokens_total": trace.get("tokens_total", 0),
        "cost": trace.get("cost", 0),
        "citations": normalized_citations,
    }


def context_payload():
    naive = contexts.naive()
    engineered = contexts.engineered()
    naive_search = next(
        tool for tool in naive.tools
        if tool["function"]["name"] == config.T_SEARCH
    )
    engineered_search = next(
        tool for tool in engineered.tools
        if tool["function"]["name"] == config.T_SEARCH
    )
    naive_properties = naive_search["function"]["parameters"].get("properties", {})
    engineered_properties = engineered_search["function"]["parameters"].get(
        "properties", {}
    )
    return {
        "naive": {
            "prompt": naive.system_prompt,
            "tool_count": len(naive.tools),
            "search_parameter_count": len(naive_properties),
            "search_parameters": list(naive_properties),
            "search_description": naive_search["function"]["description"],
        },
        "engineered": {
            "prompt": engineered.system_prompt,
            "tool_count": len(engineered.tools),
            "search_parameter_count": len(engineered_properties),
            "search_parameters": list(engineered_properties),
            "search_description": engineered_search["function"]["description"],
        },
        "transformations": [
            {
                "id": "prune",
                "label": "Prune",
                "summary": "43 → 5 search parameters",
                "detail": (
                    "Expose only query, page size, ranking, detail level, and "
                    "the C3 influence filter."
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
                "summary": "Route minimal → cite standard",
                "detail": (
                    "Use compact records while choosing a route, then request "
                    "citation-grade evidence only after a query succeeds."
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
    parser.add_argument("--qid", default="q13")
    parser.add_argument(
        "--runs-root",
        type=pathlib.Path,
        default=config.ROOT / "runs 2",
        help="frozen experiment directory to visualise (default: runs 2)",
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
                f"Generated from {runs_root.name}/A, {runs_root.name}/C, "
                "data/questions.jsonl, and circuit/contexts.py. Values are "
                "experimental artifacts, not UI fixtures."
            ),
        },
        "question": {
            "id": question["id"],
            "topic": question["topic"],
            "text": selected["A"]["question"],
            "gold_dois": question["gold_dois"],
        },
        "contexts": context_payload(),
        "runs": {
            name: trace_payload(selected[name], question)
            for name in ("A", "C")
        },
        "aggregate": {
            name: aggregate(name, traces[name], questions)
            for name in ("A", "C")
        },
    }

    # Refuse to publish a misleading comparison.
    if not payload["runs"]["A"]["schema_compliant"]:
        parser.error("selected naive trace is not schema compliant")
    if not payload["runs"]["C"]["schema_compliant"]:
        parser.error("selected engineered trace is not schema compliant")
    if payload["aggregate"]["A"]["schema_compliance"] != 1:
        parser.error("corrected naive baseline is not fully schema compliant")
    if payload["aggregate"]["C"]["cost_per_verified"] is None:
        parser.error("engineered benchmark has no verified citations")
    if payload["aggregate"]["C"]["zero_result_rate"] >= payload["aggregate"]["A"]["zero_result_rate"]:
        parser.error("engineered context does not reduce zero-result calls")
    if payload["aggregate"]["C"]["mean_tokens"] >= payload["aggregate"]["A"]["mean_tokens"]:
        parser.error("engineered context does not reduce token use")
    if math.isclose(
        payload["contexts"]["naive"]["search_parameter_count"],
        payload["contexts"]["engineered"]["search_parameter_count"],
    ):
        parser.error("context schemas are not meaningfully different")

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
