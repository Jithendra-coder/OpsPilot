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
                    con.commit()
                app.initialize()
                app.initialize()
                with app.db() as con:
                    columns = {row["name"] for row in con.execute("PRAGMA table_info(sessions)")}
                    version = con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
                self.assertTrue({"actor", "role"}.issubset(columns))
                self.assertEqual(version, 1)
            finally:
                app.DATA, app.DB_PATH = previous_data, previous_db


if __name__ == "__main__":
    unittest.main()
