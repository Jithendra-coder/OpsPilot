import sqlite3
import unittest

import app
from scripts.evaluate import FIXTURE as HELDOUT_FIXTURE, evaluate as evaluate_heldout


class DiagnosisTests(unittest.TestCase):
    def records_for(self, cause_id):
        cause = app.CAUSES[cause_id]
        return [
            {"id": "ev_" + str(index), "kind": kind, "source": source, "observation": observation, "signal_id": signal}
            for index, (signal, kind, source, observation, _severity) in enumerate(cause[3])
        ]

    def test_seed_library_has_more_than_thirty_replayable_cases(self):
        self.assertEqual(len(app.scenarios()), 36)

    def test_seeded_benchmark_matches_all_labeled_cases_and_keeps_unknown_cases_inconclusive(self):
        results = [app.evaluate_case(scenario) for scenario in app.scenarios()]
        labeled = [item for item in results if item["expected"] is not None]
        unlabeled = [item for item in results if item["expected"] is None]
        self.assertEqual(len(labeled), 28)
        self.assertTrue(all(item["correct"] for item in labeled))
        self.assertEqual(len(unlabeled), 8)
        self.assertTrue(all(item["status"] == "inconclusive" for item in unlabeled))

    def test_heldout_signature_compositions_measure_cause_selection_and_abstention(self):
        import json

        report = evaluate_heldout(json.loads(HELDOUT_FIXTURE.read_text(encoding="utf-8"))["cases"])
        self.assertEqual(report["summary"]["case_count"], 17)
        self.assertEqual(report["summary"]["supported_precision"], 1.0)
        self.assertEqual(report["summary"]["supported_recall"], 1.0)
        self.assertEqual(report["summary"]["abstention_precision"], 1.0)
        self.assertEqual(report["summary"]["abstention_recall"], 1.0)
        self.assertEqual(report["summary"]["false_supported"], 0)
        self.assertIn("after evidence has been mapped", report["limitation"])

    def test_supported_diagnosis_links_each_observation(self):
        result = app.diagnose(self.records_for("db_pool"), [])
        self.assertEqual(result["status"], "supported")
        self.assertEqual(result["cause_id"], "db_pool")
        self.assertEqual(len(result["hypotheses"][0]["evidence_ids"]), 3)

    def test_conflicting_causes_stay_inconclusive(self):
        evidence = [
            {"id": "a", "kind": "logs", "observation": "pool wait", "signal_id": "log.db_acquire_timeout"},
            {"id": "b", "kind": "metrics", "observation": "pool full", "signal_id": "metric.db_pool_saturated"},
            {"id": "c", "kind": "traces", "observation": "slow new release", "signal_id": "trace.release_slow_path"},
            {"id": "d", "kind": "changes", "observation": "release deployed", "signal_id": "change.checkout_release_recent"},
        ]
        result = app.diagnose(evidence, [])
        self.assertEqual(result["status"], "inconclusive")
        self.assertIsNone(result["root_cause"])
        self.assertEqual(len(result["hypotheses"]), 2)

    def test_unavailable_tools_prevent_a_confident_diagnosis(self):
        result = app.diagnose(self.records_for("db_pool"), [{"kind": "traces"}])
        self.assertEqual(result["status"], "inconclusive")
        self.assertLessEqual(result["confidence"], 0.58)

    def test_instruction_like_log_text_cannot_add_arbitrary_actions(self):
        case = next(item for item in app.scenarios() if any("Untrusted request text" in evidence[2] for evidence in item["plan"]))
        scenario = {"plan": app.dumps(case["plan"]), "errors": app.dumps(case["errors"])}
        evidence, errors = app.make_evidence(scenario)
        result = app.diagnose(evidence, errors)
        self.assertEqual(result["cause_id"], "db_pool")
        self.assertEqual(result["recommendation"]["sandbox_action"]["type"], "restore_db_pool_baseline")
        self.assertTrue(result["recommendation"]["approval_required"])

    def test_state_machine_rejects_skipping_triage(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute("CREATE TABLE incidents(id TEXT PRIMARY KEY,status TEXT,updated_at TEXT)")
        con.execute("CREATE TABLE incident_events(id TEXT,incident_id TEXT,kind TEXT,actor TEXT,created_at TEXT,details TEXT)")
        con.execute("CREATE TABLE audit_events(id TEXT,actor TEXT,role TEXT,action TEXT,target_id TEXT,created_at TEXT,details TEXT)")
        con.execute("INSERT INTO incidents VALUES('INC_test','NEW','')")
        with self.assertRaises(app.ApiError):
            app.set_status(con, "INC_test", "RESOLVED", {"note": "skipped verification"})
        app.set_status(con, "INC_test", "TRIAGING", {"reason": "test"})
        app.set_status(con, "INC_test", "INVESTIGATING", {"reason": "test"})
        with self.assertRaises(app.ApiError):
            app.set_status(con, "INC_test", "RESOLVED", {"verification": {"healthy": True, "symptom_cleared": True}})
        app.set_status(con, "INC_test", "ESCALATED", {"reason": "test"})
        app.set_status(con, "INC_test", "FAILED", {"reason": "test"})
        with self.assertRaises(app.ApiError):
            app.set_status(con, "INC_test", "TRIAGING", {"reason": "terminal"})
        con.close()


if __name__ == "__main__":
    unittest.main()
