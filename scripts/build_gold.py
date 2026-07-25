#!/usr/bin/env python3
"""Build the deterministic OpenAIRE gold question set.

Each topic is routed through the two complementary retrieval paths specified by
the experiment design. Their results are unioned by normalized DOI, ranked by
OpenAIRE citation count, and the top five are retained only if every DOI can be
looked up again through the OpenAIRE details tool.
"""
import concurrent.futures
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from circuit import config  # noqa: E402
from circuit.mcp_client import MCP  # noqa: E402


TOPICS = [
    ("CRISPR gene editing", ["CRISPR", "editing"]),
    ("CAR T-cell therapy", ["chimeric", "antigen", "receptor"]),
    ("mRNA vaccines", ["mRNA", "vaccine"]),
    ("immune checkpoint blockade", ["immune", "checkpoint"]),
    ("exosome biomarkers", ["exosome", "biomarker"]),
    ("gut microbiome", ["gut", "microbiome"]),
    ("Alzheimer amyloid beta", ["Alzheimer", "amyloid"]),
    ("Parkinson alpha-synuclein", ["Parkinson", "alpha-synuclein"]),
    ("cancer immunotherapy", ["cancer", "immunotherapy"]),
    ("stem cells", ["stem", "cells"]),
    ("viral-vector gene therapy", ["viral", "vector", "therapy"]),
    ("RNA interference", ["RNA", "interference", "siRNA"]),
    ("AlphaFold protein structure prediction", ["AlphaFold", "structure", "prediction"]),
    ("telomeres and aging", ["telomere", "aging"]),
    ("epigenetic regulation", ["epigenetic", "regulation"]),
    ("liquid biopsy", ["liquid", "biopsy"]),
    ("organoid disease models", ["organoid", "disease", "model"]),
    ("antibody-drug conjugates", ["antibody-drug", "conjugate", "cancer"]),
    ("NLRP3 inflammasome", ["inflammasome", "NLRP3"]),
    ("VEGF angiogenesis", ["angiogenesis", "VEGF"]),
    ("prime editing", ["prime", "editing", "pegRNA"]),
    ("metagenomic sequencing", ["metagenomic", "sequencing"]),
    ("synthetic gene circuits", ["synthetic", "biology", "circuit"]),
    ("SARS-CoV-2 spike protein", ["SARS-CoV-2", "spike"]),
    ("circadian rhythms", ["circadian", "rhythm"]),
]

DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)


def normalize_doi(value):
    if not isinstance(value, str):
        return ""
    return DOI_PREFIX.sub("", value.strip()).rstrip(".,;").lower()


def payload(text):
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def results(out):
    parsed = payload(out["text"])
    data = parsed.get("data")
    if not out["ok"] or not parsed.get("success") or not isinstance(data, dict):
        return []
    rows = data.get("results")
    return rows if isinstance(rows, list) else []


def citation_count(row):
    value = row.get("citations", row.get("citation_count", 0))
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def verified_details(mcp, doi):
    out = mcp.call(config.T_DETAILS, {"identifier": doi})
    parsed = payload(out["text"])
    data = parsed.get("data")
    if not out["ok"] or not parsed.get("success") or not isinstance(data, dict):
        return None
    if normalize_doi(data.get("doi")) != doi:
        return None
    return data


def build_topic(index, topic, terms):
    query = " ".join(terms)
    mcp = MCP()
    influence = mcp.call(config.T_INFLUENCE, {
        "influence_class": "C3",
        "query": query,
        "page_size": 10,
    })
    cited = mcp.call(config.T_SEARCH, {
        "query": query,
        "sort_by": "citationCount DESC",
        "page_size": 10,
    })

    candidates = {}
    for row in results(influence) + results(cited):
        if not isinstance(row, dict):
            continue
        doi = normalize_doi(row.get("doi"))
        title = row.get("title")
        if not doi or not isinstance(title, str) or not title.strip():
            continue
        candidate = {
            "doi": doi,
            "title": title.strip(),
            "citations": citation_count(row),
        }
        previous = candidates.get(doi)
        if previous is None or candidate["citations"] > previous["citations"]:
            candidates[doi] = candidate

    ranked = sorted(
        candidates.values(),
        key=lambda row: (-row["citations"], row["doi"]),
    )[:5]
    if len(ranked) < 5:
        return index, None, f"only {len(ranked)} DOI-bearing candidates"

    verified = []
    for candidate in ranked:
        details = verified_details(mcp, candidate["doi"])
        if details is not None:
            verified.append({
                "doi": candidate["doi"],
                "title": details.get("title") or candidate["title"],
            })
    if len(verified) < 5:
        return index, None, f"only {len(verified)}/5 top DOIs verified"

    record = {
        "id": f"q{index:02d}",
        "topic": topic,
        "query_terms": terms,
        "gold_dois": [row["doi"] for row in verified],
        "gold_titles": [row["title"] for row in verified],
    }
    return index, record, ""


def main():
    completed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(build_topic, index, topic, terms)
            for index, (topic, terms) in enumerate(TOPICS, 1)
        ]
        for future in concurrent.futures.as_completed(futures):
            index, record, reason = future.result()
            completed.append((index, record))
            topic = TOPICS[index - 1][0]
            if record:
                print(f"KEEP q{index:02d} {topic}")
            else:
                print(f"DROP q{index:02d} {topic}: {reason}")

    records = [record for _, record in sorted(completed) if record is not None]
    output = config.DATA / "questions.jsonl"
    output.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    )
    print(f"\nWrote {len(records)} verified topics to {output}")
    if len(records) != len(TOPICS):
        print("One or more topics were dropped; replace them and rerun for 25.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
