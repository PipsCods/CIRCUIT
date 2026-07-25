import json
import pathlib
import tempfile
import unittest

from circuit import config, provenance
from scripts import run_eval, score


class ProvenanceTest(unittest.TestCase):
    def test_manifest_and_trace_hash_verify_together(self):
        prompt = "system"
        schemas = [{"name": "search"}]
        manifest = {
            "run_id": "run-1",
            "git": {"commit": "abc", "dirty": False},
            "model": {"requested": "model", "gateway": "gateway"},
            "generation": {"temperature": 0.0, "seed": 7},
            "context": {
                "system_prompt": prompt,
                "system_prompt_sha256": provenance.sha256_text(prompt),
            },
            "tools": {
                "schemas": schemas,
                "sha256": provenance.sha256_json(schemas),
            },
            "questions": {
                "sha256": provenance.sha256_file(
                    config.DATA / "questions.jsonl"
                ),
                "ids": ["q01"],
            },
        }
        trace = {
            "qid": "q01",
            "run_id": "run-1",
            "manifest_sha256": provenance.sha256_json(manifest),
            "error": None,
            "reproducibility": {
                "git_commit": "abc",
                "git_dirty": False,
                "system_prompt_sha256": provenance.sha256_text(prompt),
                "tool_schema_sha256": provenance.sha256_json(schemas),
                "question_set_sha256": provenance.sha256_file(
                    config.DATA / "questions.jsonl"
                ),
                "requested_model": "model",
                "gateway": "gateway",
                "temperature": 0.0,
                "seed": 7,
            },
            "model_responses": [{
                "actual_model": "actual-model",
                "actual_provider": "actual-provider",
            }],
            "tool_calls": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            (directory / "manifest.json").write_text(json.dumps(manifest))
            status, reasons = score._verification_status(
                directory,
                [trace],
                {"q01"},
            )
        self.assertEqual(status, "verified")
        self.assertEqual(reasons, [])

    def test_evidence_files_are_content_addressed_and_immutable(self):
        digest = provenance.sha256_text("evidence")
        trace = {"_evidence_blobs": {digest: "evidence"}}
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            run_eval.persist_evidence(directory, trace)
            path = directory / "evidence" / f"{digest}.txt"
            self.assertEqual(path.read_text(), "evidence")
            self.assertNotIn("_evidence_blobs", trace)

            repeated = {"_evidence_blobs": {digest: "evidence"}}
            run_eval.persist_evidence(directory, repeated)
            collision = {"_evidence_blobs": {digest: "different"}}
            with self.assertRaisesRegex(RuntimeError, "hash collision"):
                run_eval.persist_evidence(directory, collision)


if __name__ == "__main__":
    unittest.main()
