import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import app
from fastapi.testclient import TestClient

from backend import investigation_tools
from backend.asgi import app as api


class ProductionFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = tempfile.TemporaryDirectory(prefix="opspilot-platform-")
        app.DATA = Path(cls.data.name)
        app.DB_PATH = app.DATA / "opspilot.db"

    @classmethod
    def tearDownClass(cls):
        cls.data.cleanup()

    def setUp(self):
        self.operator = TestClient(api)
        self.approver = TestClient(api)
        self.operator.__enter__()
        self.approver.__enter__()
        app.initialize()
        with app.db() as con:
            for table in ("verification_results", "action_executions", "approval_requests", "remediation_proposals",
                "lab_runs", "evidence", "run_events", "investigations", "comments", "incident_events", "sessions",
                "evaluations", "audit_events", "alerts", "incidents"):
                con.execute("DELETE FROM " + table)
        self.operator_csrf = self._login(self.operator, app.OPERATOR_PASSWORD, "operator")
        self.approver_csrf = self._login(self.approver, app.APPROVER_PASSWORD, "approver")

    def tearDown(self):
        self.operator.__exit__(None, None, None)
        self.approver.__exit__(None, None, None)

    @staticmethod
    def _login(client, password, role):
        response = client.post("/api/v1/auth/session", json={"password": password})
        assert response.status_code == 200, response.text
        assert response.json()["role"] == role
        return response.json()["csrf_token"]

    @staticmethod
    def _post(client, csrf, path, payload):
        return client.post(path, json=payload, headers={"X-CSRF-Token": csrf})

    def _incident(self):
        response = self._post(self.operator, self.operator_csrf, "/api/v1/simulations/start", {"scenario_id": app.scenarios()[0]["id"]})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["incident"]

    def test_approved_action_is_immutable_idempotent_and_verified_server_side(self):
        incident = self._incident()
        result = self._post(self.operator, self.operator_csrf, f"/api/v1/incidents/{incident['id']}/investigate", {"idempotency_key": "run-key-0001"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["investigation"]["result"]["cause_id"], "db_pool")

        proposal_response = self._post(self.operator, self.operator_csrf, f"/api/v1/incidents/{incident['id']}/remediation/propose", {})
        self.assertEqual(proposal_response.status_code, 201, proposal_response.text)
        proposal = proposal_response.json()["proposal"]
        self.assertEqual(proposal["action_type"], "restore_db_pool_baseline")
        self.assertTrue(proposal["expected_result"])
        self.assertTrue(proposal["verification"])
        self.assertIn("different approver", " ".join(proposal["prerequisites"]))
        self.assertTrue(proposal["rollback"])
        approval_detail = self.operator.get("/api/v1/approvals?status=pending").json()["approvals"][0]
        self.assertEqual(approval_detail["expected_result"], proposal["expected_result"])

        with app.db() as con:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("UPDATE remediation_proposals SET parameters=? WHERE id=?", (json.dumps({"service_id": "postgres"}), proposal["id"]))

        direct_resolution = self._post(self.operator, self.operator_csrf, f"/api/v1/incidents/{incident['id']}/status",
            {"status": "RESOLVED", "note": "checkboxes are not verification", "verification": {"healthy": True, "symptom_cleared": True}})
        self.assertEqual(direct_resolution.status_code, 409)

        denied_approval = self._post(self.operator, self.operator_csrf, f"/api/v1/approvals/{proposal['approval']['id']}/approve", {"note": "operator cannot approve"})
        self.assertEqual(denied_approval.status_code, 403)
        approval = self._post(self.approver, self.approver_csrf, f"/api/v1/approvals/{proposal['approval']['id']}/approve", {"note": "Reviewed exact isolated action"})
        self.assertEqual(approval.status_code, 200, approval.text)
        denied_execution = self._post(self.approver, self.approver_csrf, f"/api/v1/actions/{proposal['id']}/execute", {"idempotency_key": "action-key-0001"})
        self.assertEqual(denied_execution.status_code, 403)

        execution = self._post(self.operator, self.operator_csrf, f"/api/v1/actions/{proposal['id']}/execute", {"idempotency_key": "action-key-0001"})
        self.assertEqual(execution.status_code, 200, execution.text)
        self.assertTrue(execution.json()["verification"]["passed"])
        self.assertEqual(execution.json()["execution"]["scope"], "isolated_simulation")
        self.assertEqual(execution.json()["execution"]["idempotency_key"], "action-key-0001")
        execution_id = execution.json()["execution"]["id"]
        with app.db() as con:
            stored_key = con.execute("SELECT idempotency_key FROM action_executions WHERE id=?", (execution_id,)).fetchone()[0]
        self.assertEqual(stored_key, proposal["id"] + ":action-key-0001")
        self.assertEqual(self.operator.get(f"/api/v1/actions/{execution_id}/verification").status_code, 200)
        self.assertEqual(self.operator.get(f"/api/v1/actions/{proposal['id']}/verification").status_code, 200)
        self.assertEqual(self.operator.get(f"/api/v1/incidents/{incident['id']}").json()["incident"]["status"], "RESOLVED")

        retry = self._post(self.operator, self.operator_csrf, f"/api/v1/actions/{proposal['id']}/execute", {"idempotency_key": "action-key-0001"})
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertTrue(retry.json()["reused"])
        duplicate = self._post(self.operator, self.operator_csrf, f"/api/v1/actions/{proposal['id']}/execute", {"idempotency_key": "action-key-0002"})
        self.assertEqual(duplicate.status_code, 409)

    def test_read_tools_enforce_dependency_scope_and_bounded_time_ranges(self):
        incident = self._incident()
        records = investigation_tools.get_recent_logs(incident["id"], limit=10)
        self.assertTrue(records["items"])
        with self.assertRaises(app.ApiError):
            investigation_tools.get_recent_logs(incident["id"], service_id="catalog")
        with self.assertRaises(app.ApiError):
            investigation_tools.get_recent_logs(incident["id"], limit=51)
        with self.assertRaises(app.ApiError):
            investigation_tools.get_recent_logs(incident["id"], start_time="2026-01-02T00:00:00Z", end_time="2026-01-01T00:00:00Z")
        old_end = datetime.now(timezone.utc) - timedelta(days=30)
        self.assertEqual(investigation_tools.get_recent_logs(incident["id"], end_time=old_end.isoformat())["items"], [])
        with self.assertRaises(app.ApiError):
            investigation_tools.get_recent_logs(incident["id"], start_time="2026-01-01T00:00:00Z", end_time="2026-01-09T00:00:00Z")
        with self.assertRaises(app.ApiError):
            investigation_tools.get_recent_logs(incident["id"], start_time="2099-01-01T00:00:00Z")

    def test_health_reports_database_readiness(self):
        response = self.operator.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["database"], "ready")

    def test_approver_cannot_start_operator_work(self):
        response = self._post(self.approver, self.approver_csrf, "/api/v1/simulations/start", {"scenario_id": app.scenarios()[0]["id"]})
        self.assertEqual(response.status_code, 403)

    def test_untrusted_enum_types_return_client_errors(self):
        incident = self._incident()
        created = self._post(self.operator, self.operator_csrf, "/api/v1/incidents", {"title": "Malformed severity input", "severity": [],
            "service_id": "checkout", "description": "Invalid type must be rejected cleanly."})
        self.assertEqual(created.status_code, 400)
        status = self._post(self.operator, self.operator_csrf, f"/api/v1/incidents/{incident['id']}/status", {"status": [], "note": "This is not a state."})
        self.assertEqual(status.status_code, 400)

    def test_parallel_retries_share_one_investigation(self):
        incident = self._incident()
        token = self.operator.cookies.get("opspilot_session")
        headers = {"Cookie": "opspilot_session=" + token, "X-CSRF-Token": self.operator_csrf}

        def submit():
            with TestClient(api) as client:
                return client.post(f"/api/v1/incidents/{incident['id']}/investigate", json={"idempotency_key": "parallel-run-key-0001"}, headers=headers)

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _index: submit(), range(2)))
        self.assertTrue(all(response.status_code == 200 for response in responses), [response.text for response in responses])
        self.assertEqual(responses[0].json()["investigation"]["id"], responses[1].json()["investigation"]["id"])
        with app.db() as con:
            count = con.execute("SELECT COUNT(*) FROM investigations WHERE incident_id=?", (incident["id"],)).fetchone()[0]
        self.assertEqual(count, 1)

    def test_expired_approval_is_read_only_until_decision_and_can_be_replaced(self):
        incident = self._incident()
        investigation = self._post(self.operator, self.operator_csrf, f"/api/v1/incidents/{incident['id']}/investigate", {"idempotency_key": "expiry-run-key-0001"})
        self.assertEqual(investigation.status_code, 200, investigation.text)
        proposal = self._post(self.operator, self.operator_csrf, f"/api/v1/incidents/{incident['id']}/remediation/propose", {}).json()["proposal"]
        with app.db() as con:
            con.execute("UPDATE approval_requests SET expires_at='2000-01-01T00:00:00Z' WHERE id=?", (proposal["approval"]["id"],))
        expired = self.operator.get("/api/v1/approvals?status=expired")
        self.assertEqual(expired.status_code, 200, expired.text)
        self.assertEqual(expired.json()["approvals"][0]["approval_status"], "expired")
        with app.db() as con:
            status = con.execute("SELECT status FROM approval_requests WHERE id=?", (proposal["approval"]["id"],)).fetchone()[0]
        self.assertEqual(status, "pending")
        rejected_as_late = self._post(self.approver, self.approver_csrf, f"/api/v1/approvals/{proposal['approval']['id']}/approve", {"note": "Too late to approve"})
        self.assertEqual(rejected_as_late.status_code, 409)
        retry = self._post(self.operator, self.operator_csrf, f"/api/v1/incidents/{incident['id']}/investigate", {"idempotency_key": "expiry-run-key-0002"})
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["investigation"]["result"]["cause_id"], "db_pool")
        replacement = self._post(self.operator, self.operator_csrf, f"/api/v1/incidents/{incident['id']}/remediation/propose", {})
        self.assertEqual(replacement.status_code, 201, replacement.text)
        self.assertNotEqual(replacement.json()["proposal"]["id"], proposal["id"])

    def test_webhook_authentication_deduplication_and_payload_conflict(self):
        token = "local-monitoring-webhook-token-0123456789"
        payload = {"title": "Checkout alert from monitor", "severity": "P2", "service_id": "checkout",
            "description": "Checkout error rate exceeded its configured threshold.", "correlation_id": "monitor-alert-001"}
        with patch.dict("os.environ", {"OPSPILOT_ALERT_WEBHOOK_TOKEN": token}):
            denied = self.operator.post("/api/v1/webhooks/alerts", json=payload)
            self.assertEqual(denied.status_code, 401)
            headers = {"Authorization": "Bearer " + token}
            created = self.operator.post("/api/v1/webhooks/alerts", json=payload, headers=headers)
            self.assertEqual(created.status_code, 201, created.text)
            repeated = self.approver.post("/api/v1/webhooks/alerts", json=payload, headers=headers)
            self.assertEqual(repeated.status_code, 200, repeated.text)
            self.assertTrue(repeated.json()["deduplicated"])
            self.assertEqual(repeated.json()["incident"]["id"], created.json()["incident"]["id"])
            conflict = dict(payload, description="A different alert reused this correlation identifier.")
            response = self.operator.post("/api/v1/webhooks/alerts", json=conflict, headers=headers)
            self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
