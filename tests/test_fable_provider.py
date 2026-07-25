import unittest

from circuit import config, contexts, llm
from scripts.run_eval import CONFIGS


class FakeBlock:
    def __init__(self, block_type, **values):
        self.type = block_type
        for key, value in values.items():
            setattr(self, key, value)

    def model_dump(self):
        return {
            "type": self.type,
            **{
                key: value
                for key, value in vars(self).items()
                if key != "type"
            },
        }


class FakeUsage:
    input_tokens = 100
    output_tokens = 20


class FakeResponse:
    stop_reason = "tool_use"
    stop_details = None
    usage = FakeUsage()
    content = [
        FakeBlock("thinking", thinking="", signature="signed"),
        FakeBlock("tool_use", id="tool_1", name="search", input={"query": "CRISPR"}),
    ]

    def model_dump(self):
        return {
            "model": config.FABLE,
            "stop_reason": self.stop_reason,
            "content": [block.model_dump() for block in self.content],
        }


class FakeMessages:
    def __init__(self):
        self.kwargs = None
        self.response = FakeResponse()

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class FakeClient:
    def __init__(self):
        self.messages = FakeMessages()


class FableProviderTest(unittest.TestCase):
    def setUp(self):
        self.original_client = llm._client
        self.client = FakeClient()
        llm._client = self.client

    def tearDown(self):
        llm._client = self.original_client

    def test_fable_is_available_for_both_contexts(self):
        self.assertEqual(config.PROVIDER[config.FABLE], "anthropic")
        self.assertEqual(config.PRICES[config.FABLE],
                         {"in": 0.000010, "out": 0.000050})
        self.assertEqual(CONFIGS["E"], (config.FABLE, contexts.NAIVE))
        self.assertEqual(CONFIGS["F"], (config.FABLE, contexts.ENGINEERED))

    def test_fable_omits_unsupported_temperature_and_keeps_thinking(self):
        reply = llm.chat(
            config.FABLE,
            [{"role": "user", "content": "Find CRISPR papers."}],
            tools=[{
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }],
        )

        self.assertNotIn("temperature", self.client.messages.kwargs)
        self.assertEqual(reply.tool_calls, [{
            "id": "tool_1",
            "name": "search",
            "args": {"query": "CRISPR"},
        }])
        self.assertEqual(reply.provider_content[0]["type"], "thinking")

        provider_content = reply.provider_content
        _, translated, _ = llm._to_anthropic([
            {"role": "user", "content": "Find CRISPR papers."},
            {
                "role": "assistant",
                "content": reply.text,
                "tool_calls": [{
                    "id": "tool_1",
                    "type": "function",
                    "function": {
                        "name": "search",
                        "arguments": '{"query": "CRISPR"}',
                    },
                }],
                "_provider_content": provider_content,
            },
            {
                "role": "tool",
                "tool_call_id": "tool_1",
                "content": '{"results": []}',
            },
        ], [])
        self.assertEqual(translated[1]["content"], provider_content)

    def test_fable_refusal_is_not_mistaken_for_an_empty_answer(self):
        response = FakeResponse()
        response.stop_reason = "refusal"
        response.stop_details = {"type": "refusal", "category": "bio"}
        response.content = []
        self.client.messages.response = response

        with self.assertRaisesRegex(RuntimeError, "Anthropic refusal.*bio"):
            llm.chat(
                config.FABLE,
                [{"role": "user", "content": "Find papers."}],
            )

    def test_sonnet_still_receives_deterministic_temperature(self):
        llm.chat(
            config.LARGE,
            [{"role": "user", "content": "Find papers."}],
            temperature=0.0,
        )
        self.assertEqual(self.client.messages.kwargs["temperature"], 0.0)


if __name__ == "__main__":
    unittest.main()
