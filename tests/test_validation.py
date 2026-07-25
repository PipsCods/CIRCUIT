import json
import unittest

from circuit import validation


def valid_output():
    return {
        "answer": "Five grounded papers.",
        "citations": [
            {
                "doi": f"10.1000/{index}",
                "title": f"Paper {index}",
                "citation_count": index,
            }
            for index in range(5)
        ],
    }


class ExtractionTest(unittest.TestCase):
    def test_raw_json_is_kept_separate_from_recovery(self):
        payload = valid_output()
        extraction = validation.extract_json(json.dumps(payload))
        self.assertTrue(extraction.raw_parseable)
        self.assertEqual(extraction.method, "raw")
        self.assertEqual(extraction.value, payload)

    def test_fenced_and_embedded_json_are_recovered_without_repair(self):
        raw = json.dumps(valid_output())
        fenced = validation.extract_json(f"Result:\n```json\n{raw}\n```")
        embedded = validation.extract_json(f"Result:\n\n{raw}")
        self.assertFalse(fenced.raw_parseable)
        self.assertEqual(fenced.method, "fenced")
        self.assertEqual(fenced.value, valid_output())
        self.assertEqual(embedded.method, "embedded")
        self.assertEqual(embedded.value, valid_output())

    def test_braces_inside_strings_do_not_break_balanced_scan(self):
        payload = valid_output()
        payload["answer"] = 'A title can contain {"braces": "safely"}.'
        extraction = validation.extract_json(f"Here:\n{json.dumps(payload)}")
        self.assertEqual(extraction.method, "embedded")
        self.assertEqual(extraction.value, payload)

    def test_multiple_objects_are_ambiguous(self):
        extraction = validation.extract_json('{"a": 1}\n{"b": 2}')
        self.assertEqual(extraction.method, "ambiguous")
        self.assertIsNone(extraction.value)

    def test_invalid_json_is_not_repaired(self):
        extraction = validation.extract_json(
            '```json\n{"answer": "bad", "citations": [},\n```'
        )
        self.assertEqual(extraction.method, "missing")
        self.assertIsNone(extraction.value)


class ContractTest(unittest.TestCase):
    def test_valid_success_contract(self):
        self.assertEqual(validation.validate_contract(valid_output()), [])

    def test_exact_cardinality_and_field_types_are_required(self):
        payload = valid_output()
        payload["citations"] = payload["citations"][:3]
        payload["citations"][0]["doi"] = None
        payload["citations"][1]["citation_count"] = True
        errors = validation.validate_contract(payload)
        self.assertIn("citations:length_5", errors)
        self.assertIn("citations[0].doi:nonempty_string", errors)
        self.assertIn(
            "citations[1].citation_count:nonnegative_integer",
            errors,
        )

    def test_exact_keys_and_distinct_dois_are_required(self):
        payload = valid_output()
        payload["extra"] = "not allowed"
        payload["citations"][0]["extra"] = "not allowed"
        payload["citations"][1]["doi"] = payload["citations"][0]["doi"]
        errors = validation.validate_contract(payload)
        self.assertIn("top_level:keys", errors)
        self.assertIn("citations[0]:keys", errors)
        self.assertIn("citations:distinct_dois", errors)

    def test_safe_abstention_is_explicit_but_not_compliant_success(self):
        payload = {"answer": "Insufficient evidence.", "citations": []}
        self.assertTrue(validation.is_safe_abstention(payload))
        self.assertIn("citations:length_5", validation.validate_contract(payload))

    def test_tool_schema_validation_catches_types_enums_and_bool_integers(self):
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "page_size": {"type": "integer", "minimum": 1},
                "type": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["publication"]},
                },
            },
            "required": ["query"],
        }
        errors = validation.validate_schema_instance(
            {"query": "x", "page_size": True, "type": ["Article"]},
            schema,
        )
        self.assertIn("$.page_size:type", errors)
        self.assertIn("$.type[0]:enum", errors)


if __name__ == "__main__":
    unittest.main()
