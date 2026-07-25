import json
import urllib.error
import unittest
from unittest import mock

from circuit import config, llm


class FakeHTTPResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps({
            "id": "response-1",
            "model": config.SMALL,
            "provider": "test-provider",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }).encode()


class OpenRouterRetryTest(unittest.TestCase):
    def test_pre_response_transport_failure_is_retried_and_recorded(self):
        with (
            mock.patch.object(config, "OPENROUTER_KEY", "test-key"),
            mock.patch(
                "circuit.llm.urllib.request.urlopen",
                side_effect=[
                    urllib.error.URLError("temporary DNS failure"),
                    FakeHTTPResponse(),
                ],
            ),
            mock.patch("circuit.llm.time.sleep") as sleep,
        ):
            reply = llm._openrouter(
                config.SMALL,
                [{"role": "user", "content": "hello"}],
                tools=None,
                temperature=0.0,
                max_tokens=10,
                response_format=None,
                timeout=1,
            )

        self.assertEqual(reply.text, "ok")
        self.assertEqual(reply.transport_attempts, 2)
        self.assertEqual(reply.actual_provider, "test-provider")
        sleep.assert_called_once_with(config.TRANSPORT_RETRY_DELAYS[0])


if __name__ == "__main__":
    unittest.main()
