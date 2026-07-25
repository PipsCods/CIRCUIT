#!/usr/bin/env python3
"""Run one CIRCUIT experiment configuration over the frozen question set."""
import argparse
import concurrent.futures
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from circuit import agent, config, contexts, doi  # noqa: E402


CONFIGS = {
    "N": (config.SMALL, contexts.NONE),
    "A": (config.SMALL, contexts.NAIVE),
    "B": (config.LARGE, contexts.NAIVE),
    "C": (config.SMALL, contexts.ENGINEERED),
    "D": (config.LARGE, contexts.ENGINEERED),
    "E": (config.FABLE, contexts.NAIVE),
    "F": (config.FABLE, contexts.ENGINEERED),
}


def question_text(topic):
    return (
        f"What are the most influential papers on {topic}? "
        "Return 5 with DOIs and citation counts."
    )


def citation_dois(parsed):
    if not isinstance(parsed, dict):
        return []
    citations = parsed.get("citations")
    if not isinstance(citations, list):
        return []
    return [
        citation.get("doi")
        for citation in citations
        if isinstance(citation, dict) and isinstance(citation.get("doi"), str)
    ]


def evaluate(config_name, model, context, question):
    prompt = question_text(question["topic"])
    try:
        trace = agent.run(model, context, prompt)
        trace["error"] = None
    except Exception as exc:
        trace = {
            "tool_calls": [],
            "final_text": "",
            "parsed": None,
            "parse_error": "run failed",
            "turns": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "tokens_total": 0,
            "cost": 0.0,
            "doi_checks": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
    else:
        trace["doi_checks"] = []
        resolution_errors = []
        for value in citation_dois(trace["parsed"]):
            try:
                trace["doi_checks"].append(doi.resolve(value))
            except Exception as exc:
                resolution_errors.append(
                    f"{value}: {type(exc).__name__}: {exc}"
                )
        trace["resolution_errors"] = resolution_errors
    return {
        "config": config_name,
        "qid": question["id"],
        "topic": question["topic"],
        "question": prompt,
        "model": model,
        "context": context.name,
        **trace,
    }


def write_trace(directory, trace):
    path = directory / f"{trace['qid']}.json"
    temporary = directory / f".{trace['qid']}.tmp"
    temporary.write_text(json.dumps(trace, indent=2, ensure_ascii=False))
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", choices=sorted(CONFIGS))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--qid", action="append", default=None,
        help="Run only these question ids (repeatable). Smoke-testing only — "
             "a scored matrix must run the whole frozen set.")
    args = parser.parse_args()

    config_name = args.config.upper()
    model, context_factory = CONFIGS[config_name]
    questions = [
        json.loads(line)
        for line in (config.DATA / "questions.jsonl").read_text().splitlines()
        if line.strip()
    ]
    # Validate the selection before any network work, so a mistyped id fails
    # instantly instead of after schema fetch and OAuth.
    if args.qid:
        wanted = list(dict.fromkeys(args.qid))
        by_id = {question["id"]: question for question in questions}
        missing = [qid for qid in wanted if qid not in by_id]
        if missing:
            parser.error(f"unknown question ids: {', '.join(missing)}")
        # Keep frozen-set order so a subset run is a slice, not a reordering.
        selected = set(wanted)
        questions = [q for q in questions if q["id"] in selected]
        print(f"PARTIAL RUN: {len(questions)} of 25 questions — not a scoreable matrix")

    context = context_factory()
    output = config.RUNS / config_name
    output.mkdir(parents=True, exist_ok=True)

    print(
        f"Running {config_name}: {model} + {context.name} "
        f"over {len(questions)} questions with {args.workers} workers"
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(evaluate, config_name, model, context, question)
            for question in questions
        ]
        for future in concurrent.futures.as_completed(futures):
            trace = future.result()
            write_trace(output, trace)
            status = "ERROR" if trace["error"] else "DONE"
            print(
                f"{status} {trace['qid']}  turns={trace['turns']} "
                f"calls={len(trace['tool_calls'])} "
                f"tokens={trace['tokens_total']} cost=${trace['cost']:.6f}"
            )

    # Only the questions this invocation ran — globbing the directory would fold
    # in stale traces from an earlier run and misreport the tally.
    errors = [
        question["id"] for question in questions
        if json.loads((output / f"{question['id']}.json").read_text()).get("error")
    ]
    print(f"Finished {config_name}: {len(questions) - len(errors)}/{len(questions)} runs")
    if errors:
        print(f"Errored: {', '.join(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
