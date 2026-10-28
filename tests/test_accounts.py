import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from backend.asgi import app as api
from scripts import accounts
from fastapi.testclient import TestClient


class TeamAccountTests(unittest.TestCase):
    def setUp(self):
        self.previous_data, self.previous_db = app.DATA, app.DB_PATH
        self.data = tempfile.TemporaryDirectory(prefix="opspilot-accounts-")
        app.DATA = Path(self.data.name)
        app.DB_PATH = app.DATA / "opspilot.db"
        self.database_url = patch.dict(os.environ, {"OPSPILOT_DATABASE_URL": ""})
        self.database_url.start()
        app.initialize()
        with app.db() as con:
            for table in ("sessions", "audit_events", "users"):
                con.execute("DELETE FROM " + table)
        self.client = TestClient(api)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.database_url.stop()
        app.DATA, app.DB_PATH = self.previous_data, self.previous_db
        self.data.cleanup()

    def test_account_admin_creates_hashes_revokes_sessions_and_disables_access(self):
        legacy = self.client.post("/api/v1/auth/session", json={"password": app.OPERATOR_PASSWORD})
        self.assertEqual(legacy.status_code, 200, legacy.text)
        with patch("scripts.accounts.getpass.getpass", side_effect=["account-password-2026", "account-password-2026"]):
            with contextlib.redirect_stdout(io.StringIO()):
                accounts.main(["add", "--username", "Analyst", "--role", "operator"])
        self.assertEqual(self.client.get("/api/v1/auth/session").status_code, 401)
        with app.db() as con:
            user = con.execute("SELECT * FROM users WHERE username='analyst'").fetchone()
        self.assertEqual(user["role"], "operator")
        self.assertNotEqual(user["password_hash"], "account-password-2026")
        self.assertEqual(self.client.post("/api/v1/auth/session",
            json={"username": "ANALYST", "password": "account-password-2026"}).json()["user"], "analyst")
        with patch("scripts.accounts.getpass.getpass", side_effect=["new-account-password-2026", "new-account-password-2026"]):
            with contextlib.redirect_stdout(io.StringIO()):
                accounts.main(["set-password", "--username", "analyst"])
        self.assertEqual(self.client.get("/api/v1/auth/session").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/session",
            json={"username": "analyst", "password": "new-account-password-2026"}).status_code, 200)
        with contextlib.redirect_stdout(io.StringIO()):
            accounts.main(["disable", "--username", "analyst"])
        self.assertEqual(self.client.get("/api/v1/auth/session").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/session",
            json={"username": "analyst", "password": "new-account-password-2026"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
