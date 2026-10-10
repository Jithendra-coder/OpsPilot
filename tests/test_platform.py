import json
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

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
                "lab_runs", "evidence", "incident_observations", "run_events", "investigations", "comments", "incident_events", "sessions",
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

    @staticmethod
    def _external_payload():
        payload = json.loads((Path(__file__).parent / "fixtures" / "normalized-evidence.json").read_text(encoding="utf-8"))
        for item in payload["evidence"]:
            item["observed_at"] = app.now()
        return payload

    def test_approved_action_is_immutable_idempotent_and_verified_server_side(self):
        incident = self._incident()
        result = self._post(self.operator, self.operator_csrf, f"/api/v1/incidents/{incident['id']}/investigate", {"idempotency_key": "run-key-0001"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["investigation"]["result"]["cause_id"], "db_pool")
        tool_steps = self.operator.get(f"/api/v1/incidents/{incident['id']}/report").json()["report"]["tool_timeline"]
        self.assertEqual({step["stage"] for step in tool_steps if step["stage"].startswith("tool:")},
            {"tool:incident_intake", "tool:get_recent_logs", "tool:query_error_metrics", "tool:get_request_traces",
                "tool:get_deployment_history", "tool:llm_hypothesis_review"})

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

    def test_introduction_get_started_and_console_assets_are_served(self):
        intro = self.operator.get("/")
        self.assertEqual(intro.status_code, 200)
        self.assertIn('href="/console">Get started', intro.text)
        self.assertIn("Content-Security-Policy", intro.headers)
        console = self.operator.get("/console")
        self.assertEqual(console.status_code, 200)
        self.assertIn('id="login-form"', console.text)
        for asset in ("/app.css", "/app.js", "/intro.css", "/demo-poster.svg", "/demo-captions.vtt"):
            with self.subTest(asset=asset):
                self.assertEqual(self.operator.get(asset).status_code, 200)

    def test_login_throttle_is_atomic_expires_and_stays_bounded(self):
        prefix = "rate-test-" + uuid4().hex
        address = prefix + "-parallel"
        stamp = time.monotonic()
        barrier = Barrier(20)
        with app.LOGIN_ATTEMPTS_LOCK:
            previous_prune = app.LOGIN_ATTEMPTS_LAST_PRUNE

        def reserve(_index):
            barrier.wait(timeout=5)
            return app._reserve_login_attempt(address, stamp)

        try:
            with ThreadPoolExecutor(max_workers=20) as pool:
                allowed = list(pool.map(reserve, range(20)))
            self.assertEqual(sum(allowed), app.LOGIN_ATTEMPT_LIMIT)
            self.assertFalse(app._reserve_login_attempt(address, stamp + 30))
            self.assertTrue(app._reserve_login_attempt(address, stamp + app.LOGIN_LOCK_SECONDS + 1))

            for index in range(app.LOGIN_MAX_ADDRESSES + 2):
                app._reserve_login_attempt(prefix + "-" + str(index), stamp + app.LOGIN_LOCK_SECONDS + 2)
            with app.LOGIN_ATTEMPTS_LOCK:
                self.assertLessEqual(len(app.LOGIN_ATTEMPTS), app.LOGIN_MAX_ADDRESSES)
        finally:
            with app.LOGIN_ATTEMPTS_LOCK:
                for key in [key for key in app.LOGIN_ATTEMPTS if key.startswith(prefix)]:
                    app.LOGIN_ATTEMPTS.pop(key, None)
                app.LOGIN_ATTEMPTS_LAST_PRUNE = previous_prune

    def test_login_endpoint_throttles_repeated_bad_passwords(self):
        try:
            for _ in range(app.LOGIN_ATTEMPT_LIMIT):
                response = self.operator.post("/api/v1/auth/session", json={"password": "incorrect test password"})
                self.assertEqual(response.status_code, 401, response.text)
            blocked = self.operator.post("/api/v1/auth/session", json={"password": "incorrect test password"})
            self.assertEqual(blocked.status_code, 429, blocked.text)
        finally:
            app._clear_login_attempts("testclient")

    def test_evaluation_report_discloses_its_fixture_scope(self):
        response = self._post(self.operator, self.operator_csrf, "/api/v1/evaluations", {})
        self.assertEqual(response.status_code, 201, response.text)
        report = response.json()["evaluation"]["report"]
        self.assertEqual(report["evaluation_type"], "seeded_signature_consistency")
        self.assertIn("not accuracy on independent incidents", report["limitation"])
        self.assertNotIn("expected", self.operator.get("/api/v1/scenarios").json()["scenarios"][0])

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
            "description": "Checkout error rate exceeded its configured threshold.", "correlation_id": "monitor-alert-001",
            "evidence": [{"kind": "logs", "service_id": "checkout", "source": "checkout-api",
                "observation": "A checkout request waited for a connection.", "observed_at": app.now(),
                "severity": "error", "signal_id": "log.db_acquire_timeout"}]}
        with patch.dict("os.environ", {"OPSPILOT_ALERT_WEBHOOK_TOKEN": token}):
            denied = self.operator.post("/api/v1/webhooks/alerts", json=payload)
            self.assertEqual(denied.status_code, 401)
            headers = {"Authorization": "Bearer " + token}
            created = self.operator.post("/api/v1/webhooks/alerts", json=payload, headers=headers)
            self.assertEqual(created.status_code, 201, created.text)
            self.assertEqual(created.json()["evidence_received"], 1)
            repeated = self.approver.post("/api/v1/webhooks/alerts", json=payload, headers=headers)
            self.assertEqual(repeated.status_code, 200, repeated.text)
            self.assertTrue(repeated.json()["deduplicated"])
            self.assertEqual(repeated.json()["incident"]["id"], created.json()["incident"]["id"])
            conflict = dict(payload, description="A different alert reused this correlation identifier.")
            response = self.operator.post("/api/v1/webhooks/alerts", json=conflict, headers=headers)
            self.assertEqual(response.status_code, 409)
            with app.db() as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM incident_observations WHERE incident_id=?", (created.json()["incident"]["id"],)).fetchone()[0], 1)

    def test_manual_evidence_intake_investigation_and_multiple_records_per_kind(self):
        payload = self._external_payload()
        created = self._post(self.operator, self.operator_csrf, "/api/v1/incidents", payload)
        self.assertEqual(created.status_code, 201, created.text)
        incident = created.json()["incident"]
        self.assertEqual(created.json()["evidence_received"], 4)
        self.assertIsNone(incident["scenario_id"])
        self.assertEqual(len(self.operator.get(f"/api/v1/incidents/{incident['id']}/evidence").json()["evidence"]), 4)

        investigation = self._post(self.operator, self.operator_csrf,
            f"/api/v1/incidents/{incident['id']}/investigate", {"idempotency_key": "manual-evidence-run-01"})
        self.assertEqual(investigation.status_code, 200, investigation.text)
        result = investigation.json()["investigation"]["result"]
        self.assertEqual(result["status"], "supported")
        self.assertEqual(result["cause_id"], "db_pool")
        report = self.operator.get(f"/api/v1/incidents/{incident['id']}/report").json()["report"]
        self.assertEqual(len(report["evidence"]), 4)
        self.assertEqual(sum(item["kind"] == "logs" for item in report["evidence"]), 2)
        self.assertEqual({item["provenance"] for item in report["evidence"]}, {"operator-submitted"})
        with app.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM evidence WHERE run_id=?", (investigation.json()["investigation"]["id"],)).fetchone()[0], 4)
        denied_action = self._post(self.operator, self.operator_csrf,
            f"/api/v1/incidents/{incident['id']}/remediation/propose", {})
        self.assertEqual(denied_action.status_code, 409)
        self.assertEqual(denied_action.json()["error"]["code"], "sandbox_only")

    def test_prometheus_metrics_join_submitted_logs_in_the_investigation_report(self):
        payload = self._external_payload()
        payload["evidence"] = [item for item in payload["evidence"] if item["kind"] == "logs"][:1]
        created = self._post(self.operator, self.operator_csrf, "/api/v1/incidents", payload)
        self.assertEqual(created.status_code, 201, created.text)
        incident = created.json()["incident"]
        metric = {"incident_id": incident["id"], "correlation_id": incident["correlation_id"], "kind": "metrics",
            "service_id": "checkout", "source": "prometheus:metric.db_pool_saturated",
            "observation": "Configured PromQL signal matched at value 0.97", "signal_id": "metric.db_pool_saturated",
            "severity": "warning", "observed_at": app.now(), "provenance": "prometheus-http-api"}
        with patch.object(investigation_tools.prometheus, "collect", return_value=[metric]) as collect:
            response = self._post(self.operator, self.operator_csrf,
                f"/api/v1/incidents/{incident['id']}/investigate", {"idempotency_key": "prometheus-run-0001"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["investigation"]["result"]["cause_id"], "db_pool")
        collect.assert_called_once()
        report = self.operator.get(f"/api/v1/incidents/{incident['id']}/report").json()["report"]
        self.assertIn("prometheus-http-api", {item["provenance"] for item in report["evidence"]})

    def test_evidence_intake_rejects_out_of_scope_and_mismatched_signals_atomically(self):
        payload = self._external_payload()
        payload["evidence"][0]["service_id"] = "catalog"
        denied = self._post(self.operator, self.operator_csrf, "/api/v1/incidents", payload)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["error"]["code"], "service_scope_denied")
        with app.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM incidents").fetchone()[0], 0)

        payload = self._external_payload()
        payload["evidence"][0]["signal_id"] = "metric.db_pool_saturated"
        invalid = self._post(self.operator, self.operator_csrf, "/api/v1/incidents", payload)
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["error"]["code"], "invalid_signal_id")
        with app.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM incidents").fetchone()[0], 0)

        for timestamp, code in (
            ((datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(), "invalid_observation_time"),
            ((datetime.now(timezone.utc) - timedelta(days=8)).isoformat(), "observation_too_old"),
        ):
            payload = self._external_payload()
            payload["evidence"][0]["observed_at"] = timestamp
            invalid = self._post(self.operator, self.operator_csrf, "/api/v1/incidents", payload)
            self.assertEqual(invalid.status_code, 400)
            self.assertEqual(invalid.json()["error"]["code"], code)
            with app.db() as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM incidents").fetchone()[0], 0)

    def test_manual_evidence_can_be_attached_only_before_first_investigation(self):
        created = self._post(self.operator, self.operator_csrf, "/api/v1/incidents", {
            "title": "Checkout evidence follow-up", "severity": "P2", "service_id": "checkout",
            "description": "A monitoring alert needs evidence."})
        self.assertEqual(created.status_code, 201, created.text)
        incident_id = created.json()["incident"]["id"]
        evidence = self._external_payload()["evidence"]
        empty = self._post(self.operator, self.operator_csrf, f"/api/v1/incidents/{incident_id}/evidence", {"evidence": []})
        self.assertEqual(empty.status_code, 400)
        attached = self._post(self.operator, self.operator_csrf, f"/api/v1/incidents/{incident_id}/evidence", {"evidence": evidence})
        self.assertEqual(attached.status_code, 201, attached.text)
        self.assertEqual(attached.json()["evidence_received"], 4)
        retried = self._post(self.operator, self.operator_csrf, f"/api/v1/incidents/{incident_id}/evidence", {"evidence": evidence})
        self.assertEqual(retried.status_code, 201, retried.text)
        self.assertEqual(retried.json()["evidence_received"], 0)
        extra = []
        for index in range(22):
            item = dict(evidence[index % len(evidence)])
            item["source"] += "-" + str(index)
            item["observation"] += " Additional record " + str(index) + "."
            extra.append(item)
        overflow = self._post(self.operator, self.operator_csrf, f"/api/v1/incidents/{incident_id}/evidence",
            {"evidence": extra})
        self.assertEqual(overflow.status_code, 400)
        self.assertEqual(overflow.json()["error"]["code"], "evidence_limit")
        with app.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM incident_observations WHERE incident_id=?", (incident_id,)).fetchone()[0], 4)
        run = self._post(self.operator, self.operator_csrf,
            f"/api/v1/incidents/{incident_id}/investigate", {"idempotency_key": "attached-evidence-run-01"})
        self.assertEqual(run.status_code, 200, run.text)
        late = self._post(self.operator, self.operator_csrf, f"/api/v1/incidents/{incident_id}/evidence", {"evidence": evidence[:1]})
        self.assertEqual(late.status_code, 409)
        self.assertEqual(late.json()["error"]["code"], "evidence_window_closed")

    def test_insufficient_external_evidence_abstains(self):
        payload = self._external_payload()
        payload["evidence"] = payload["evidence"][:1]
        created = self._post(self.operator, self.operator_csrf, "/api/v1/incidents", payload)
        self.assertEqual(created.status_code, 201, created.text)
        incident_id = created.json()["incident"]["id"]
        run = self._post(self.operator, self.operator_csrf,
            f"/api/v1/incidents/{incident_id}/investigate", {"idempotency_key": "incomplete-evidence-run-01"})
        self.assertEqual(run.status_code, 200, run.text)
        result = run.json()["investigation"]["result"]
        self.assertEqual(result["status"], "inconclusive")
        self.assertIsNone(result["root_cause"])


if __name__ == "__main__":
    unittest.main()
