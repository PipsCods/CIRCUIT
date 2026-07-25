import json
import unittest

from circuit import evidence


class EvidenceTest(unittest.TestCase):
    def test_extracts_compact_records_from_openaire_envelope(self):
        text = json.dumps({
            "success": True,
            "data": {
                "results": [
                    {
                        "doi": "10.1000/example",
                        "title": "An Example",
                        "citations": 42,
                        "abstract": "Deliberately excluded from the ledger.",
                    },
                    {
                        "doi": "10.1000/metrics",
                        "title": "Metrics Example",
                        "metrics": {"citation_count": 9},
                    },
                ],
            },
        })
        self.assertEqual(evidence.extract_tool_evidence(text), [
            {
                "doi": "10.1000/example",
                "title": "An Example",
                "citation_count": 42,
            },
            {
                "doi": "10.1000/metrics",
                "title": "Metrics Example",
                "citation_count": 9,
            },
        ])

    def test_grounding_requires_title_and_count_on_the_same_record(self):
        citation = {
            "doi": "https://doi.org/10.1000/EXAMPLE",
            "title": "  An   Example ",
            "citation_count": 42,
        }
        ledger = [
            {
                "doi": "10.1000/example",
                "title": "An Example",
                "citation_count": 41,
            },
            {
                "doi": "10.1000/example",
                "title": "Different Title",
                "citation_count": 42,
            },
        ]
        result = evidence.grounding_for(citation, ledger)
        self.assertTrue(result["doi_grounded"])
        self.assertTrue(result["title_agrees"])
        self.assertTrue(result["citation_count_agrees"])
        self.assertFalse(result["record_grounded"])


if __name__ == "__main__":
    unittest.main()
