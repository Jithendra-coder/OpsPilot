from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from scripts import demo, demo_accounts


class DemoAccountTests(unittest.TestCase):
    def setUp(self):
        self.previous_data, self.previous_db = app.DATA, app.DB_PATH
        self.temp = tempfile.TemporaryDirectory(prefix="opspilot-demo-accounts-")
        app.DATA = Path(self.temp.name)
        app.DB_PATH = app.DATA / "opspilot.db"
        self.database_url = patch.dict(os.environ, {"OPSPILOT_DATABASE_URL": ""})
        self.database_url.start()
        app.initialize()

    def tearDown(self):
        self.database_url.stop()
        app.DATA, app.DB_PATH = self.previous_data, self.previous_db
        self.temp.cleanup()

    def test_demo_accounts_are_created_once_and_configuration_conflicts_fail(self):
        demo_accounts.ensure_account("operator", "operator", "demo-operator-password-2026")
        demo_accounts.ensure_account("reviewer", "approver", "demo-reviewer-password-2026")
        demo_accounts.ensure_account("operator", "operator", "a-new-password-that-does-not-rotate")
        with app.db() as con:
            rows = con.execute("SELECT username,role,active FROM users ORDER BY username").fetchall()
        self.assertEqual([(row["username"], row["role"], row["active"]) for row in rows],
            [("operator", "operator", 1), ("reviewer", "approver", 1)])
        with self.assertRaises(SystemExit):
            demo_accounts.ensure_account("operator", "approver", "demo-operator-password-2026")


class DemoCredentialTests(unittest.TestCase):
    def test_credentials_and_alert_token_are_generated_once(self):
        with tempfile.TemporaryDirectory(prefix="opspilot-demo-config-") as directory:
            state = Path(directory)
            with patch.object(demo, "STATE", state), patch.object(demo, "ENV_FILE", state / "demo.env"), patch.object(demo, "TOKEN_FILE", state / "alertmanager-token"):
                demo.ensure_local_credentials()
                first = demo.ENV_FILE.read_text(encoding="utf-8")
                token = demo.TOKEN_FILE.read_text(encoding="utf-8")
                demo.ensure_local_credentials()
                self.assertEqual(demo.ENV_FILE.read_text(encoding="utf-8"), first)
                values = dict(line.split("=", 1) for line in first.splitlines())
                self.assertGreaterEqual(len(values["OPSPILOT_OPERATOR_PASSWORD"]), 16)
                self.assertGreaterEqual(len(values["OPSPILOT_APPROVER_PASSWORD"]), 16)
                self.assertNotEqual(values["OPSPILOT_OPERATOR_PASSWORD"], values["OPSPILOT_APPROVER_PASSWORD"])
                self.assertGreaterEqual(len(token), 32)
                self.assertEqual(token, values["OPSPILOT_ALERT_WEBHOOK_TOKEN"])

    def test_up_recreates_compose_services_without_removing_volumes(self):
        with patch.object(demo, "ensure_local_credentials"), patch.object(demo, "wait_for_app"), \
                patch.object(demo, "compose") as compose:
            self.assertEqual(demo.main(["up"]), 0)
        self.assertEqual([call.args for call in compose.call_args_list],
            [("down",), ("up", "--build", "--detach")])


if __name__ == "__main__":
    unittest.main()
