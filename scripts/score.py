#!/usr/bin/env python3
"""Deterministically score every available CIRCUIT run configuration."""
import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from circuit import config, doi  # noqa: E402
from scripts.run_eval import CONFIGS  # noqa: E402


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


def metrics(name, traces, gold):
    n = len(traces)
    tool_calls = [call for trace in traces for call in trace.get("tool_calls", [])]
    checks = []
    for trace in traces:
        existing = {
            doi.normalize(check.get("doi")): check
            for check in trace.get("doi_checks", [])
        }
        for value in returned_dois(trace.get("parsed")):
            checks.append(existing.get(value) or doi.resolve(value))
    verified = sum(
        bool(check.get("resolves_openaire") or check.get("resolves_crossref"))
        for check in checks
    )
    openaire = sum(bool(check.get("resolves_openaire")) for check in checks)
    crossref = sum(bool(check.get("resolves_crossref")) for check in checks)
    gold_hits = 0
    for trace in traces:
        predicted = set(returned_dois(trace.get("parsed"))[:5])
        gold_hits += len(predicted & set(gold[trace["qid"]]["gold_dois"]))

    total_cost = sum(float(trace.get("cost", 0)) for trace in traces)
    return {
        "config": name,
        "n": n,
        "validity": verified / len(checks) if checks else 0.0,
        "openaire": openaire / len(checks) if checks else 0.0,
        "crossref": crossref / len(checks) if checks else 0.0,
        "gold_recall": gold_hits / (5 * n) if n else 0.0,
        # No retrieval calls is a distinct experimental condition, not a 0%
        # zero-result rate. Keep it out of the denominator and display N/A.
        "zero_rate": (
            sum(call.get("n_results") == 0 for call in tool_calls) / len(tool_calls)
            if tool_calls else None
        ),
        "schema": (
            sum(trace.get("parse_error") is None for trace in traces) / n
            if n else 0.0
        ),
        "mean_tokens": (
            sum(int(trace.get("tokens_total", 0)) for trace in traces) / n
            if n else 0.0
        ),
        "cost": total_cost,
        "verified": verified,
        "cost_per_verified": total_cost / verified if verified else math.inf,
    }


def pct(value):
    return f"{100 * value:.1f}%"


def money(value):
    return "∞" if math.isinf(value) else f"${value:.6f}"


def main():
    questions = [
        json.loads(line)
        for line in (config.DATA / "questions.jsonl").read_text().splitlines()
        if line.strip()
    ]
    gold = {question["id"]: question for question in questions}
    rows = []
    for name in sorted(CONFIGS):
        directory = config.RUNS / name
        if not directory.exists():
            continue
        traces = [
            json.loads(path.read_text())
            for path in sorted(directory.glob("q*.json"))
        ]
        if traces:
            rows.append(metrics(name, traces, gold))

    if not rows:
        print("No runs found.")
        return 1

    headers = (
        "Cfg", "N", "DOI valid", "Gold R@5", "Zero calls",
        "Schema", "Mean tok", "Total cost", "$/verified",
    )
    formatted = []
    for row in rows:
        formatted.append((
            row["config"],
            str(row["n"]),
            pct(row["validity"]),
            pct(row["gold_recall"]),
            pct(row["zero_rate"]) if row["zero_rate"] is not None else "N/A",
            pct(row["schema"]),
            f"{row['mean_tokens']:.0f}",
            money(row["cost"]),
            money(row["cost_per_verified"]),
        ))
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in formatted))
        for index in range(len(headers))
    ]
    print("  ".join(value.ljust(widths[i]) for i, value in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in formatted:
        print("  ".join(value.ljust(widths[i]) for i, value in enumerate(row)))

    print("\nResolution source rates (reported separately; validity is their union):")
    for row in rows:
        print(
            f"  {row['config']}: OpenAIRE={pct(row['openaire'])}, "
            f"Crossref={pct(row['crossref'])}, verified citations={row['verified']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
