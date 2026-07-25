#!/usr/bin/env python3
"""Run one CIRCUIT experiment configuration over the frozen question set."""
import argparse
import concurrent.futures
import datetime
import json
import pathlib
import re
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from circuit import agent, config, contexts, doi, provenance, validation  # noqa: E402


CONFIGS = {
    "A": (config.SMALL, contexts.NAIVE),
    "B": (config.LARGE, contexts.NAIVE),
    "C": (config.SMALL, contexts.ENGINEERED),
    "D": (config.LARGE, contexts.ENGINEERED),
    "E": (config.FABLE, contexts.NAIVE),
    "F": (config.FABLE, contexts.ENGINEERED),
    "G": (config.SMALL, contexts.INTRINSIC),
    "H": (config.LARGE, contexts.INTRINSIC),
    "I": (config.FABLE, contexts.INTRINSIC),
    "J": (config.OPUS, contexts.INTRINSIC),
}
CONFIG_ALIASES = {
    "gemma-no-tools": "G",
    "gemma-naive-mcp": "A",
    "gemma-engineered-mcp": "C",
    "opus-no-tools": "J",
}
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def resolve_config(value):
    """Return the artifact label, model, and context factory for a CLI name."""
    alias = value.lower()
    if alias in CONFIG_ALIASES:
        key = CONFIG_ALIASES[alias]
        label = alias
    else:
        key = value.upper()
        label = key
    model, context_factory = CONFIGS[key]
    return label, model, context_factory


def question_text(topic):
    return (
        f"What are the most influential papers on {topic}? "
        "Return 5 with DOIs and citation counts."
    )


def citation_dois(extracted):
    return [
        citation.get("doi")
        for citation in validation.citation_objects(extracted)
        if isinstance(citation, dict) and isinstance(citation.get("doi"), str)
    ]


def evaluate(config_name, model, context, question, run_metadata):
    prompt = question_text(question["topic"])
    try:
        trace = agent.run(model, context, prompt)
        trace["error"] = None
    except Exception as exc:
        trace = {
            "tool_calls": [],
            "evidence_ledger": [],
            "_evidence_blobs": {},
            "model_responses": [],
            "final_text": "",
            "parsed": None,
            "parse_error": "run failed",
            "extracted": None,
            "extraction_method": "missing",
            "contract_errors": ["response:run_failed"],
            "safe_abstention": False,
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
        for value in citation_dois(trace["extracted"]):
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
        "run_id": run_metadata["run_id"],
        "timestamp": provenance.utc_now(),
        "manifest_sha256": run_metadata["manifest_sha256"],
        "reproducibility": {
            "git_commit": run_metadata["git_commit"],
            "git_dirty": run_metadata["git_dirty"],
            "system_prompt_sha256": run_metadata["system_prompt_sha256"],
            "tool_schema_sha256": run_metadata["tool_schema_sha256"],
            "question_set_sha256": run_metadata["question_set_sha256"],
            "requested_model": model,
            "gateway": config.PROVIDER.get(model, "openrouter"),
            "temperature": (
                None if model in config.NO_TEMPERATURE else config.TEMPERATURE
            ),
            "seed": (
                config.SEED
                if config.PROVIDER.get(model, "openrouter") == "openrouter"
                else None
            ),
        },
        **trace,
    }


def persist_evidence(directory, trace):
    blobs = trace.pop("_evidence_blobs", {})
    evidence_directory = directory / "evidence"
    evidence_directory.mkdir(exist_ok=True)
    for digest, content in blobs.items():
        path = evidence_directory / f"{digest}.txt"
        if path.exists():
            if path.read_text() != content:
                raise RuntimeError(f"evidence hash collision at {path}")
            continue
        path.write_text(content)


def write_trace(directory, trace):
    persist_evidence(directory, trace)
    path = directory / f"{trace['qid']}.json"
    temporary = directory / f".{trace['qid']}.tmp"
    temporary.write_text(json.dumps(trace, indent=2, ensure_ascii=False))
    temporary.replace(path)


def default_run_id():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def build_manifest(run_id, config_name, model, context, questions):
    question_path = config.DATA / "questions.jsonl"
    git = provenance.git_info(config.ROOT)
    prompt_hash = provenance.sha256_text(context.system_prompt)
    tool_hash = provenance.sha256_json(context.tools)
    manifest = {
        "schema_version": 2,
        "run_id": run_id,
        "config": config_name,
        "created_at": provenance.utc_now(),
        "git": git,
        "model": {
            "requested": model,
            "gateway": config.PROVIDER.get(model, "openrouter"),
        },
        "generation": {
            "temperature": (
                None if model in config.NO_TEMPERATURE else config.TEMPERATURE
            ),
            "seed": (
                config.SEED
                if config.PROVIDER.get(model, "openrouter") == "openrouter"
                else None
            ),
            "max_tokens": config.MAX_TOKENS,
            "max_turns": config.MAX_TURNS,
            "transport_max_attempts": config.TRANSPORT_MAX_ATTEMPTS,
            "transport_retry_delays_seconds": list(
                config.TRANSPORT_RETRY_DELAYS
            ),
        },
        "context": {
            "name": context.name,
            "system_prompt": context.system_prompt,
            "system_prompt_sha256": prompt_hash,
        },
        "tools": {
            "schemas": context.tools,
            "sha256": tool_hash,
        },
        "questions": {
            "path": str(question_path.relative_to(config.ROOT)),
            "sha256": provenance.sha256_file(question_path),
            "ids": [question["id"] for question in questions],
        },
        "price_per_token_usd": config.PRICES[model],
    }
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "config",
        choices=sorted([*CONFIGS, *CONFIG_ALIASES]),
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="permit a run from an uncommitted worktree (manifest remains unverified)",
    )
    args = parser.parse_args()

    config_name, model, context_factory = resolve_config(args.config)
    context = context_factory()
    questions = [
        json.loads(line)
        for line in (config.DATA / "questions.jsonl").read_text().splitlines()
        if line.strip()
    ]
    run_id = args.run_id or default_run_id()
    if not RUN_ID.fullmatch(run_id):
        parser.error("run ID must contain only letters, numbers, dot, underscore, or dash")

    manifest = build_manifest(run_id, config_name, model, context, questions)
    if manifest["git"]["dirty"] and not args.allow_dirty:
        parser.error("worktree is dirty; commit first or pass --allow-dirty")

    output = config.RUNS / "experiments" / run_id / config_name
    if output.exists():
        parser.error(f"immutable run directory already exists: {output}")
    output.mkdir(parents=True)
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    run_metadata = {
        "run_id": run_id,
        "manifest_sha256": provenance.sha256_json(manifest),
        "git_commit": manifest["git"]["commit"],
        "git_dirty": manifest["git"]["dirty"],
        "system_prompt_sha256": manifest["context"]["system_prompt_sha256"],
        "tool_schema_sha256": manifest["tools"]["sha256"],
        "question_set_sha256": manifest["questions"]["sha256"],
    }

    print(
        f"Running {config_name} in {run_id}: {model} + {context.name} "
        f"over {len(questions)} questions with {args.workers} workers"
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(
                evaluate,
                config_name,
                model,
                context,
                question,
                run_metadata,
            )
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

    errors = [
        path for path in output.glob("q*.json")
        if json.loads(path.read_text()).get("error")
    ]
    print(f"Finished {config_name}: {len(questions) - len(errors)}/{len(questions)} runs")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
