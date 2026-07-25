import unittest
from unittest import mock

from circuit import agent, config, contexts, llm
from scripts import run_eval, score


class IntrinsicBaselineTest(unittest.TestCase):
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
            "parsed": {"answer": "Known papers", "citations": []},
            "parse_error": None,
            "tool_calls": [],
            "tokens_total": 30,
            "cost": 0.001,
        }]
        gold = {"q01": {"gold_dois": []}}

        result = score.metrics("G", traces, gold)

        self.assertIsNone(result["zero_rate"])
        self.assertEqual(result["schema"], 1.0)
        self.assertEqual(result["mean_tokens"], 30)
        self.assertEqual(result["cost"], 0.001)

    @mock.patch("scripts.run_eval.doi.resolve")
    @mock.patch("scripts.run_eval.agent.run")
    def test_evaluate_preserves_question_and_trace_shape(self, run, resolve):
        run.return_value = {
            "tool_calls": [],
            "final_text": '{"answer":"Known papers","citations":[]}',
            "parsed": {"answer": "Known papers", "citations": []},
            "parse_error": None,
            "turns": 1,
            "tokens_in": 20,
            "tokens_out": 10,
            "tokens_total": 30,
            "cost": 0.001,
        }
        question = {"id": "q01", "topic": "CRISPR gene editing"}
        context = contexts.INTRINSIC()

        trace = run_eval.evaluate("G", config.SMALL, context, question)

        expected = run_eval.question_text(question["topic"])
        run.assert_called_once_with(config.SMALL, context, expected)
        resolve.assert_not_called()
        self.assertEqual(trace["question"], expected)
        self.assertEqual(trace["context"], "intrinsic")
        self.assertEqual(trace["doi_checks"], [])
        self.assertIsNone(trace["error"])


if __name__ == "__main__":
    unittest.main()
