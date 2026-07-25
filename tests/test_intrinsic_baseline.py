import unittest
from unittest import mock

from circuit import agent, config, contexts, llm
from scripts import run_eval, score


class IntrinsicBaselineTest(unittest.TestCase):
    def test_readable_cli_aliases_resolve_to_named_artifacts(self):
        expected = {
            "gemma-no-tools": (config.SMALL, contexts.INTRINSIC),
            "gemma-naive-mcp": (config.SMALL, contexts.NAIVE),
            "gemma-engineered-mcp": (config.SMALL, contexts.ENGINEERED),
            "opus-no-tools": (config.OPUS, contexts.INTRINSIC),
        }

        for alias, (model, context_factory) in expected.items():
            with self.subTest(alias=alias):
                label, resolved_model, resolved_context = (
                    run_eval.resolve_config(alias)
                )
                self.assertEqual(label, alias)
                self.assertEqual(resolved_model, model)
                self.assertIs(resolved_context, context_factory)

    def test_letter_configs_remain_backward_compatible(self):
        label, model, context_factory = run_eval.resolve_config("G")

        self.assertEqual(label, "G")
        self.assertEqual(model, config.SMALL)
        self.assertIs(context_factory, contexts.INTRINSIC)

    def test_intrinsic_configs_cover_all_models(self):
        self.assertEqual(
            run_eval.CONFIGS["G"], (config.SMALL, contexts.INTRINSIC)
        )
        self.assertEqual(
            run_eval.CONFIGS["H"], (config.LARGE, contexts.INTRINSIC)
        )
        self.assertEqual(
            run_eval.CONFIGS["I"], (config.FABLE, contexts.INTRINSIC)
        )
        self.assertEqual(
            run_eval.CONFIGS["J"], (config.OPUS, contexts.INTRINSIC)
        )

    def test_intrinsic_context_reuses_output_contract_without_tools(self):
        context = contexts.INTRINSIC()

        self.assertEqual(context.name, "intrinsic")
        self.assertEqual(context.tools, [])
        self.assertIn(contexts.OUTPUT_CONTRACT, context.system_prompt)
        self.assertIn(contexts.OUTPUT_CONTRACT, contexts.ENGINEERED_PROMPT)
        self.assertIn("knowledge stored in the model", context.system_prompt)

    @mock.patch("circuit.agent.MCP")
    @mock.patch("circuit.agent.llm.chat")
    def test_intrinsic_run_never_constructs_mcp(self, chat, mcp):
        chat.return_value = llm.Reply(
            text='{"answer":"Known papers","citations":[]}',
            tokens_in=20,
            tokens_out=10,
            cost=0.001,
        )

        trace = agent.run(
            config.SMALL,
            contexts.INTRINSIC(),
            run_eval.question_text("CRISPR gene editing"),
        )

        mcp.assert_not_called()
        chat.assert_called_once()
        self.assertEqual(chat.call_args.kwargs["tools"], [])
        self.assertEqual(trace["tool_calls"], [])
        self.assertEqual(trace["turns"], 1)
        self.assertEqual(
            trace["parsed"],
            {"answer": "Known papers", "citations": []},
        )

    def test_intrinsic_trace_is_score_compatible_without_zero_call_rate(self):
        traces = [{
            "qid": "q01",
            "context": "intrinsic",
            "final_text": '{"answer":"Insufficient recall","citations":[]}',
            "parsed": {"answer": "Known papers", "citations": []},
            "parse_error": None,
            "tool_calls": [],
            "evidence_ledger": [],
            "doi_checks": [],
            "tokens_total": 30,
            "cost": 0.001,
        }]
        gold = {"q01": {"gold_dois": []}}

        result = score.metrics("G", traces, gold)

        self.assertEqual(result["raw_json"], 1.0)
        self.assertEqual(result["safe_abstention"], 1.0)
        self.assertIsNone(result["valid_call_rate"])
        self.assertIsNone(result["successful_empty_rate"])
        self.assertEqual(result["evidence_trace_coverage"], 0.0)
        self.assertIsNone(result["record_grounded"])
        self.assertIsNone(result["cost_per_verified"])
        self.assertEqual(result["mean_tokens"], 30)
        self.assertEqual(result["cost"], 0.001)

    @mock.patch("scripts.run_eval.doi.resolve")
    @mock.patch("scripts.run_eval.agent.run")
    def test_evaluate_preserves_question_and_trace_shape(self, run, resolve):
        run.return_value = {
            "tool_calls": [],
            "evidence_ledger": [],
            "_evidence_blobs": {},
            "model_responses": [],
            "final_text": '{"answer":"Known papers","citations":[]}',
            "parsed": {"answer": "Known papers", "citations": []},
            "parse_error": None,
            "extracted": {"answer": "Known papers", "citations": []},
            "extraction_method": "raw",
            "contract_errors": ["citations:length_5"],
            "safe_abstention": True,
            "turns": 1,
            "tokens_in": 20,
            "tokens_out": 10,
            "tokens_total": 30,
            "cost": 0.001,
        }
        question = {"id": "q01", "topic": "CRISPR gene editing"}
        context = contexts.INTRINSIC()
        run_metadata = {
            "run_id": "test-run",
            "manifest_sha256": "manifest-hash",
            "git_commit": "git-hash",
            "git_dirty": False,
            "system_prompt_sha256": "prompt-hash",
            "tool_schema_sha256": "schema-hash",
            "question_set_sha256": "questions-hash",
        }

        trace = run_eval.evaluate(
            "G", config.SMALL, context, question, run_metadata
        )

        expected = run_eval.question_text(question["topic"])
        run.assert_called_once_with(config.SMALL, context, expected)
        resolve.assert_not_called()
        self.assertEqual(trace["question"], expected)
        self.assertEqual(trace["context"], "intrinsic")
        self.assertEqual(trace["doi_checks"], [])
        self.assertIsNone(trace["error"])


if __name__ == "__main__":
    unittest.main()
