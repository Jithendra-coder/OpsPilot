import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from scripts.accounts import add_account
from scripts.migrate_to_postgres import migrate


@unittest.skipUnless(os.environ.get("OPSPILOT_DATABASE_URL"), "requires the PostgreSQL integration job")
class PostgreSQLMigrationTests(unittest.TestCase):
    def setUp(self):
        app.initialize()
        with app.db() as con:
            for table in ("verification_results", "action_executions", "approval_requests", "remediation_proposals",
                "lab_runs", "evidence", "incident_observations", "run_events", "investigations", "comments",
                "incident_events", "sessions", "evaluations", "audit_events", "alerts", "incidents", "users"):
                con.execute("DELETE FROM " + table)

    def _source(self, pending=False):
        temporary = tempfile.TemporaryDirectory(prefix="opspilot-pg-migration-source-")
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        previous_data, previous_db = app.DATA, app.DB_PATH
        try:
            app.DATA, app.DB_PATH = directory, directory / "opspilot.db"
            with patch.dict(os.environ, {"OPSPILOT_DATABASE_URL": ""}):
                app.initialize()
                with app.db() as con:
                    incident_id = app.add_incident(con, "Checkout database pool saturated", "P1", "checkout",
                        "The checkout database pool is exhausted and requests are failing.", "on-call", "manual",
                        correlation_id="migration-correlation-001")
                    if pending:
                        con.execute("INSERT INTO investigations VALUES(?,?,?,?,?,?,?)",
                            ("INV_pending", incident_id, "migration-key-0001", "failed", app.now(), app.now(), "{}"))
                add_account("migration-operator", "operator", "migration-operator-password")
        finally:
            app.DATA, app.DB_PATH = previous_data, previous_db
        return directory

    def test_migrates_operational_records_and_keeps_sqlite_source(self):
        source = self._source()
        counts = migrate(source, os.environ["OPSPILOT_DATABASE_URL"])
        self.assertGreaterEqual(counts["incidents"], 1)
        self.assertTrue((source / "opspilot.db").is_file())
        with app.db() as con:
            incident = con.execute("SELECT id FROM incidents WHERE correlation_id='migration-correlation-001'").fetchone()
            user = con.execute("SELECT username FROM users WHERE username='migration-operator'").fetchone()
        self.assertIsNotNone(incident)
        self.assertIsNotNone(user)
        with self.assertRaisesRegex(ValueError, "fresh target"):
            migrate(source, os.environ["OPSPILOT_DATABASE_URL"])

    def test_refuses_to_migrate_interrupted_workflow_state(self):
        source = self._source(pending=True)
        with self.assertRaisesRegex(ValueError, "running/failed"):
            migrate(source, os.environ["OPSPILOT_DATABASE_URL"])
        with app.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM incidents").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
