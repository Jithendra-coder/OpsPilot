import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from backend import workflow


class WorkflowRecoveryTests(unittest.TestCase):
    def test_interrupted_graph_retries_from_saved_checkpoint(self):
        with tempfile.TemporaryDirectory(prefix="opspilot-workflow-") as root:
            previous_data, previous_db = app.DATA, app.DB_PATH
            app.DATA = Path(root)
            app.DB_PATH = app.DATA / "opspilot.db"
            try:
                app.initialize()
                scenario = app.scenarios()[0]
                with app.db() as con:
                    stored = con.execute("SELECT * FROM scenarios WHERE id=?", (scenario["id"],)).fetchone()
                    incident_id = app.add_incident(con, stored["title"], stored["severity"], stored["service_id"],
                        stored["description"], "Test operator", "simulation", stored["id"])
                    stamp = app.now()
                    state = {"scenario_id": stored["id"], "fault_active": True, "services": {stored["service_id"]: {"status": "degraded"}}}
                    con.execute("INSERT INTO lab_runs VALUES(?,?,?,?,?,?,?, ?,1)",
                        (app.ident("LAB"), incident_id, stored["id"], stored["expected"], 1, app.dumps(state), stamp, stamp))

                calls = {"logs": 0, "metrics": 0}
                original_logs, original_metrics = workflow.read_logs, workflow.read_metrics

                def counted_logs(graph_state):
                    calls["logs"] += 1
                    return original_logs(graph_state)

                def fail_metrics_once(graph_state):
                    calls["metrics"] += 1
                    if calls["metrics"] == 1:
                        raise RuntimeError("simulated process interruption")
                    return original_metrics(graph_state)

                with patch.object(workflow, "read_logs", side_effect=counted_logs), patch.object(workflow, "read_metrics", side_effect=fail_metrics_once):
                    with self.assertRaises(app.ApiError):
                        app.investigate(incident_id, "resume-after-failure-1")
                    result = app.investigate(incident_id, "resume-after-failure-1")

                self.assertEqual(calls["logs"], 1)
                self.assertEqual(calls["metrics"], 2)
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["result"]["cause_id"], "db_pool")
                with app.db() as con:
                    count = con.execute("SELECT COUNT(*) FROM investigations WHERE incident_id=?", (incident_id,)).fetchone()[0]
                self.assertEqual(count, 1)
            finally:
                app.DATA, app.DB_PATH = previous_data, previous_db


if __name__ == "__main__":
    unittest.main()
