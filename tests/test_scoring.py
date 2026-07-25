import json
import unittest

from scripts import score


def citations():
    return [
        {
            "doi": f"10.1000/{index}",
            "title": f"Paper {index}",
            "citation_count": index,
        }
        for index in range(5)
    ]


class ScoringTest(unittest.TestCase):
    def test_recovered_json_scores_semantics_but_not_raw_protocol(self):
        records = citations()
        final_text = "Here is the result:\n```json\n" + json.dumps({
            "answer": "Five papers.",
            "citations": records,
        }) + "\n```"
        trace = {
            "qid": "q01",
            "final_text": final_text,
            "tool_calls": [{
                "ok": True,
                "n_results": 5,
                "status": "success_nonempty",
                "argument_schema_errors": [],
            }],
            "evidence_ledger": [dict(record) for record in records],
            "doi_checks": [
                {
                    "doi": record["doi"],
                    "resolves_openaire": True,
                    "resolves_crossref": False,
                }
                for record in records
            ],
            "tokens_total": 100,
            "cost": 0.01,
        }
        gold = {"q01": {"gold_dois": [record["doi"] for record in records]}}
        row = score.metrics("X", [trace], gold, "verified")
        self.assertEqual(row["raw_json"], 0.0)
        self.assertEqual(row["structural"], 1.0)
        self.assertEqual(row["strict_contract"], 0.0)
        self.assertEqual(row["gold_recall"], 1.0)
        self.assertEqual(row["record_grounded"], 1.0)
        self.assertEqual(row["verified_grounded"], 5)
        self.assertAlmostEqual(row["cost_per_verified"], 0.002)

    def test_legacy_failed_call_is_not_a_successful_empty_call(self):
        trace = {
            "qid": "q01",
            "final_text": json.dumps({
                "answer": "Insufficient evidence.",
                "citations": [],
            }),
            "tool_calls": [{"ok": False, "n_results": 0, "args": {}}],
            "doi_checks": [],
            "tokens_total": 1,
            "cost": 0,
        }
        gold = {"q01": {"gold_dois": []}}
        row = score.metrics("X", [trace], gold)
        self.assertEqual(row["valid_call_rate"], 0.0)
        self.assertEqual(row["successful_empty_rate"], 0.0)
        self.assertEqual(row["failed_call_rate"], 1.0)
        self.assertEqual(row["call_status_counts"], {"tool_error": 1})


if __name__ == "__main__":
    unittest.main()
