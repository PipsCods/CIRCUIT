#!/usr/bin/env python3
"""Offline, deterministic scoring for legacy and immutable CIRCUIT runs."""
import argparse
import collections
import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from circuit import config, evidence, provenance, validation  # noqa: E402


def _call_status(call):
    status = call.get("status")
    if isinstance(status, str) and status:
        return status
    args = call.get("args")
    if isinstance(args, dict) and "__malformed__" in args:
        return "malformed_arguments"
    if call.get("error") == "unknown tool":
        return "unknown_tool"
    if call.get("ok") is True:
        return "success_empty" if call.get("n_results") == 0 else "success_nonempty"
    return "tool_error"


def _resolution_map(trace):
    out = {}
    for check in trace.get("doi_checks", []):
        if not isinstance(check, dict):
            continue
        normalized = validation.normalize_doi(check.get("doi"))
        if normalized:
            out[normalized] = check
    return out


def _resolved(check):
    return bool(
        check
        and (check.get("resolves_openaire") or check.get("resolves_crossref"))
    )


def metrics(name, traces, gold, metadata_status="legacy/unverified"):
    n = len(traces)
    required_slots = 5 * n
    tool_calls = [call for trace in traces for call in trace.get("tool_calls", [])]
    status_counts = collections.Counter(_call_status(call) for call in tool_calls)
    successful_calls = (
        status_counts["success_nonempty"] + status_counts["success_empty"]
    )

    raw_count = 0
    structural_count = 0
    strict_count = 0
    abstentions = 0
    extraction_counts = collections.Counter()
    gold_hits = 0
    emitted_dois = 0
    resolution_checked = 0
    resolved_dois = 0
    evidence_trace_count = 0
    grounding_evaluated = 0
    doi_grounded = 0
    title_agrees = 0
    count_agrees = 0
    records_grounded = 0
    verified_grounded = 0

    for trace in traces:
        extraction = validation.extract_json(trace.get("final_text", ""))
        extraction_counts[extraction.method] += 1
        if extraction.raw_parseable:
            raw_count += 1
        contract_errors = validation.validate_contract(extraction.value)
        if not contract_errors:
            structural_count += 1
            if extraction.raw_parseable:
                strict_count += 1
        if validation.is_safe_abstention(extraction.value):
            abstentions += 1

        citations = validation.citation_objects(extraction.value)
        predicted = {
            validation.normalize_doi(citation.get("doi"))
            for citation in citations
            if validation.normalize_doi(citation.get("doi"))
        }
        gold_hits += len(
            predicted
            & {
                validation.normalize_doi(value)
                for value in gold[trace["qid"]]["gold_dois"]
            }
        )

        resolutions = _resolution_map(trace)
        # Intrinsic configurations deliberately have no retrieval evidence.
        # Their DOI resolution and gold overlap remain scoreable, while tool
        # and grounding metrics must stay N/A rather than becoming misleading
        # zeroes merely because the trace shape includes an empty ledger.
        intrinsic = (
            trace.get("context") == "intrinsic"
            or name in {"G", "H", "I"}
        )
        has_evidence = (
            not intrinsic
            and isinstance(trace.get("evidence_ledger"), list)
        )
        ledger = trace.get("evidence_ledger", []) if has_evidence else []
        if has_evidence:
            evidence_trace_count += 1

        for citation in citations:
            normalized = validation.normalize_doi(citation.get("doi"))
            if not normalized:
                continue
            emitted_dois += 1
            check = resolutions.get(normalized)
            if check is not None:
                resolution_checked += 1
                if _resolved(check):
                    resolved_dois += 1

            if not has_evidence:
                continue
            grounding_evaluated += 1
            grounded = evidence.grounding_for(citation, ledger)
            doi_grounded += grounded["doi_grounded"]
            title_agrees += grounded["title_agrees"]
            count_agrees += grounded["citation_count_agrees"]
            records_grounded += grounded["record_grounded"]
            if grounded["record_grounded"] and _resolved(check):
                verified_grounded += 1

    total_cost = sum(float(trace.get("cost", 0)) for trace in traces)
    schema_evaluated_calls = sum(
        "argument_schema_errors" in call
        for call in tool_calls
    )
    schema_invalid_calls = sum(
        bool(call.get("argument_schema_errors"))
        for call in tool_calls
    )
    failed_calls = len(tool_calls) - successful_calls

    return {
        "config": name,
        "status": metadata_status,
        "n": n,
        "raw_json": raw_count / n if n else None,
        "structural": structural_count / n if n else None,
        "strict_contract": strict_count / n if n else None,
        "safe_abstention": abstentions / n if n else None,
        "extraction_counts": dict(extraction_counts),
        "gold_recall": gold_hits / required_slots if required_slots else None,
        "doi_presence": emitted_dois / required_slots if required_slots else None,
        "doi_validity": (
            resolved_dois / resolution_checked if resolution_checked else None
        ),
        "resolution_coverage": (
            resolution_checked / emitted_dois if emitted_dois else None
        ),
        "tool_calls": len(tool_calls),
        "valid_call_rate": (
            successful_calls / len(tool_calls) if tool_calls else None
        ),
        "successful_empty_rate": (
            status_counts["success_empty"] / len(tool_calls)
            if tool_calls else None
        ),
        "failed_call_rate": (
            failed_calls / len(tool_calls) if tool_calls else None
        ),
        "malformed_call_rate": (
            status_counts["malformed_arguments"] / len(tool_calls)
            if tool_calls else None
        ),
        "schema_invalid_call_rate": (
            schema_invalid_calls / len(tool_calls)
            if tool_calls and schema_evaluated_calls == len(tool_calls)
            else None
        ),
        "schema_validation_coverage": (
            schema_evaluated_calls / len(tool_calls) if tool_calls else None
        ),
        "call_status_counts": dict(status_counts),
        "evidence_trace_coverage": (
            evidence_trace_count / n if n else None
        ),
        "grounding_coverage": (
            grounding_evaluated / emitted_dois if emitted_dois else None
        ),
        "doi_grounded": (
            doi_grounded / grounding_evaluated
            if grounding_evaluated else None
        ),
        "title_agreement": (
            title_agrees / grounding_evaluated
            if grounding_evaluated else None
        ),
        "citation_count_agreement": (
            count_agrees / grounding_evaluated
            if grounding_evaluated else None
        ),
        "record_grounded": (
            records_grounded / grounding_evaluated
            if grounding_evaluated else None
        ),
        "verified_grounded": (
            verified_grounded if evidence_trace_count else None
        ),
        "verified_grounded_yield": (
            verified_grounded / required_slots
            if required_slots and evidence_trace_count else None
        ),
        "mean_tokens": (
            sum(int(trace.get("tokens_total", 0)) for trace in traces) / n
            if n else None
        ),
        "cost": total_cost,
        "cost_per_verified": (
            total_cost / verified_grounded
            if verified_grounded
            else (math.inf if evidence_trace_count else None)
        ),
    }


def _verification_status(directory, traces, expected_ids):
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        return "legacy/unverified", ["manifest missing"]

    reasons = []
    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return "unverified", [f"manifest unreadable: {exc}"]

    manifest_hash = provenance.sha256_json(manifest)
    if manifest.get("git", {}).get("dirty") is not False:
        reasons.append("worktree was dirty")
    if not manifest.get("git", {}).get("commit"):
        reasons.append("git commit missing")
    context = manifest.get("context", {})
    if provenance.sha256_text(context.get("system_prompt", "")) != context.get(
        "system_prompt_sha256"
    ):
        reasons.append("system prompt hash mismatch")
    tools = manifest.get("tools", {})
    if provenance.sha256_json(tools.get("schemas", [])) != tools.get("sha256"):
        reasons.append("tool schema hash mismatch")
    questions = manifest.get("questions", {})
    if questions.get("sha256") != provenance.sha256_file(
        config.DATA / "questions.jsonl"
    ):
        reasons.append("question set hash mismatch")
    if set(questions.get("ids", [])) != expected_ids:
        reasons.append("manifest question IDs incomplete or unexpected")

    trace_ids = {trace.get("qid") for trace in traces}
    if trace_ids != expected_ids:
        reasons.append("question IDs incomplete or unexpected")
    for trace in traces:
        if trace.get("run_id") != manifest.get("run_id"):
            reasons.append(f"{trace.get('qid')}: run ID mismatch")
        if trace.get("manifest_sha256") != manifest_hash:
            reasons.append(f"{trace.get('qid')}: manifest hash mismatch")
        reproducibility = trace.get("reproducibility", {})
        expected_reproducibility = {
            "git_commit": manifest.get("git", {}).get("commit"),
            "git_dirty": manifest.get("git", {}).get("dirty"),
            "system_prompt_sha256": context.get("system_prompt_sha256"),
            "tool_schema_sha256": tools.get("sha256"),
            "question_set_sha256": questions.get("sha256"),
            "requested_model": manifest.get("model", {}).get("requested"),
            "gateway": manifest.get("model", {}).get("gateway"),
            "temperature": manifest.get("generation", {}).get("temperature"),
            "seed": manifest.get("generation", {}).get("seed"),
        }
        if reproducibility != expected_reproducibility:
            reasons.append(f"{trace.get('qid')}: reproducibility metadata mismatch")

        responses = trace.get("model_responses")
        if trace.get("error") is None and not responses:
            reasons.append(f"{trace.get('qid')}: model response metadata missing")
        for response in responses or []:
            if not response.get("actual_model") or not response.get("actual_provider"):
                reasons.append(
                    f"{trace.get('qid')}: actual provider/model metadata missing"
                )

        for call in trace.get("tool_calls", []):
            response_hash = call.get("response_sha256")
            response_ref = call.get("response_ref")
            if not response_hash or not response_ref:
                reasons.append(f"{trace.get('qid')}: tool evidence reference missing")
                continue
            evidence_path = directory / response_ref
            if (
                evidence_path.parent != directory / "evidence"
                or not evidence_path.exists()
                or provenance.sha256_file(evidence_path) != response_hash
            ):
                reasons.append(f"{trace.get('qid')}: tool evidence hash mismatch")

    return ("unverified", reasons) if reasons else ("verified", [])


def _load_rows(run_id=None):
    questions = [
        json.loads(line)
        for line in (config.DATA / "questions.jsonl").read_text().splitlines()
        if line.strip()
    ]
    gold = {question["id"]: question for question in questions}
    expected_ids = set(gold)

    if run_id:
        root = config.RUNS / "experiments" / run_id
        if not root.exists():
            raise FileNotFoundError(f"run not found: {root}")
        candidates = [
            (path.name, path)
            for path in sorted(root.iterdir())
            if path.is_dir()
        ]
    else:
        candidates = [
            (name, config.RUNS / name)
            for name in ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J")
            if (config.RUNS / name).exists()
        ]

    rows = []
    notes = {}
    for name, directory in candidates:
        traces = [
            json.loads(path.read_text())
            for path in sorted(directory.glob("q*.json"))
        ]
        if not traces:
            continue
        status, reasons = _verification_status(directory, traces, expected_ids)
        rows.append(metrics(name, traces, gold, status))
        notes[name] = reasons
    return rows, notes


def pct(value):
    return "n/a" if value is None else f"{100 * value:.1f}%"


def money(value):
    if value is None:
        return "n/a"
    return "∞" if math.isinf(value) else f"${value:.6f}"


def _print_table(headers, rows):
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    print("  ".join(value.ljust(widths[index]) for index, value in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def print_report(rows, notes):
    print("Output protocol and retrieval")
    headers = (
        "Cfg", "Status", "N", "Raw JSON", "Structure", "Strict",
        "Abstain", "Gold R@5", "DOI present", "DOI valid", "DOI checks",
    )
    formatted = [
        (
            row["config"], row["status"], str(row["n"]), pct(row["raw_json"]),
            pct(row["structural"]), pct(row["strict_contract"]),
            pct(row["safe_abstention"]), pct(row["gold_recall"]),
            pct(row["doi_presence"]), pct(row["doi_validity"]),
            pct(row["resolution_coverage"]),
        )
        for row in rows
    ]
    _print_table(headers, formatted)

    print("\nTool and grounding quality")
    headers = (
        "Cfg", "Calls", "Valid calls", "Successful empty", "Failed",
        "Malformed", "Schema-invalid", "Evidence", "DOI grounded",
        "Title match", "Count match", "Record grounded",
    )
    formatted = [
        (
            row["config"], str(row["tool_calls"]), pct(row["valid_call_rate"]),
            pct(row["successful_empty_rate"]), pct(row["failed_call_rate"]),
            pct(row["malformed_call_rate"]), pct(row["schema_invalid_call_rate"]),
            pct(row["grounding_coverage"]), pct(row["doi_grounded"]),
            pct(row["title_agreement"]), pct(row["citation_count_agreement"]),
            pct(row["record_grounded"]),
        )
        for row in rows
    ]
    _print_table(headers, formatted)

    print("\nEfficiency")
    headers = (
        "Cfg", "Mean tok", "Total cost", "Verified grounded",
        "Verified yield", "$/verified",
    )
    formatted = [
        (
            row["config"], f"{row['mean_tokens']:.0f}", money(row["cost"]),
            (
                "n/a"
                if row["verified_grounded"] is None
                else str(row["verified_grounded"])
            ),
            pct(row["verified_grounded_yield"]),
            money(row["cost_per_verified"]),
        )
        for row in rows
    ]
    _print_table(headers, formatted)

    print("\nExtraction and call outcomes")
    for row in rows:
        print(
            f"  {row['config']}: extraction={row['extraction_counts']}; "
            f"calls={row['call_status_counts']}"
        )
    for name, reasons in notes.items():
        if reasons:
            print(f"  {name}: {', '.join(reasons)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        rows, notes = _load_rows(args.run_id)
    except FileNotFoundError as exc:
        parser.error(str(exc))
    if not rows:
        print("No runs found.")
        return 1
    if args.json:
        print(json.dumps({"rows": rows, "notes": notes}, indent=2))
    else:
        print_report(rows, notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
