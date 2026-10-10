import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import app


class MigrationTests(unittest.TestCase):
    def test_legacy_sessions_upgrade_once_and_record_schema_version(self):
        with tempfile.TemporaryDirectory(prefix="opspilot-migration-") as root:
            previous_data, previous_db = app.DATA, app.DB_PATH
            app.DATA = Path(root)
            app.DB_PATH = app.DATA / "opspilot.db"
            try:
                with closing(sqlite3.connect(app.DB_PATH)) as con:
                    con.execute("CREATE TABLE sessions(token_hash TEXT PRIMARY KEY,csrf TEXT NOT NULL,created_at TEXT NOT NULL,expires_at TEXT NOT NULL)")
                    con.execute("CREATE TABLE investigations(id TEXT PRIMARY KEY,incident_id TEXT NOT NULL,idempotency_key TEXT NOT NULL,status TEXT NOT NULL,started_at TEXT NOT NULL,completed_at TEXT,result TEXT,UNIQUE(incident_id,idempotency_key))")
                    con.execute("INSERT INTO investigations VALUES('run_legacy','incident_legacy','key-legacy','completed','2026-01-01T00:00:00Z','2026-01-01T00:00:01Z','{}')")
                    con.execute("CREATE TABLE evidence(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,kind TEXT NOT NULL,source TEXT NOT NULL,observed_at TEXT NOT NULL,payload TEXT NOT NULL,signal_id TEXT,UNIQUE(run_id,kind),FOREIGN KEY(run_id) REFERENCES investigations(id) ON DELETE CASCADE)")
                    con.execute("INSERT INTO evidence VALUES('ev_legacy','run_legacy','logs','collector','2026-01-01T00:00:00Z','{}',NULL)")
                    con.commit()
                app.initialize()
                app.initialize()
                with app.db() as con:
                    columns = {row["name"] for row in con.execute("PRAGMA table_info(sessions)")}
                    version = con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
                    preserved = con.execute("SELECT id FROM evidence WHERE run_id='run_legacy'").fetchone()[0]
                    con.execute("INSERT INTO evidence VALUES('ev_legacy_2','run_legacy','logs','collector-2','2026-01-01T00:00:02Z','{}',NULL)")
                self.assertTrue({"actor", "role"}.issubset(columns))
                self.assertEqual(version, 2)
                self.assertEqual(preserved, "ev_legacy")
            finally:
                app.DATA, app.DB_PATH = previous_data, previous_db


if __name__ == "__main__":
    unittest.main()
