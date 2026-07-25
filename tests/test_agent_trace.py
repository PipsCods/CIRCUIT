import json
import types
import unittest
from unittest import mock

from circuit import agent, llm


class FakeMCP:
    def __init__(self):
        self.calls = 0

    def call(self, name, args):
        self.calls += 1
        if self.calls == 1:
            text = json.dumps({"error": "invalid type"})
            return {
                "ok": False,
                "text": text,
                "n_results": None,
                "cached": True,
                "cache_key": "bad",
                "response_sha256": "a" * 64,
                "error_kind": "tool_error",
            }
        text = json.dumps({
            "success": True,
            "data": {"results": []},
            "summary": {"results_returned": 0},
        })
        return {
            "ok": True,
            "text": text,
            "n_results": 0,
            "cached": True,
            "cache_key": "empty",
            "response_sha256": "b" * 64,
        }


class AgentTraceTest(unittest.TestCase):
    def test_call_outcomes_schema_errors_and_abstention_are_recorded(self):
        tool = {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "type": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["publication"],
                            },
                        },
                    },
                    "required": ["query"],
                },
            },
        }
        context = types.SimpleNamespace(system_prompt="system", tools=[tool])
        replies = [
            llm.Reply(
                text="",
                tool_calls=[
                    {
                        "id": "bad",
                        "name": "search",
                        "args": {"query": "x", "type": ["Article"]},
                    },
                    {
                        "id": "empty",
                        "name": "search",
                        "args": {"query": "none"},
                    },
                ],
                gateway="openrouter",
                actual_provider="test-provider",
                actual_model="test-model",
            ),
            llm.Reply(
                text=json.dumps({
                    "answer": "Insufficient evidence.",
                    "citations": [],
                }),
                gateway="openrouter",
                actual_provider="test-provider",
                actual_model="test-model",
            ),
        ]

        with (
            mock.patch("circuit.agent.llm.chat", side_effect=replies),
            mock.patch("circuit.agent.MCP", return_value=FakeMCP()),
        ):
            trace = agent.run("requested-model", context, "question")

        self.assertEqual(
            [call["status"] for call in trace["tool_calls"]],
            ["schema_invalid", "success_empty"],
        )
        self.assertEqual(
            trace["tool_calls"][0]["argument_schema_errors"],
            ["$.type[0]:enum"],
        )
        self.assertIsNone(trace["tool_calls"][0]["n_results"])
        self.assertEqual(trace["tool_calls"][1]["n_results"], 0)
        self.assertTrue(trace["safe_abstention"])
        self.assertIn("citations:length_5", trace["contract_errors"])
        self.assertEqual(trace["model_responses"][0]["actual_model"], "test-model")
        self.assertEqual(len(trace["_evidence_blobs"]), 2)


if __name__ == "__main__":
    unittest.main()
