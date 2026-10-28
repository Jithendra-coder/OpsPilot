import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx

import app
from backend import alertmanager, loki, prometheus, tempo


class AlertmanagerNormalizationTests(unittest.TestCase):
    def test_normalizes_firing_and_resolved_alerts_to_stable_incident_keys(self):
        started = app.now()
        alert = {"fingerprint": "a" * 40, "startsAt": started,
            "labels": {"service_id": "checkout", "severity": "critical", "alertname": "PoolSaturated"},
            "annotations": {"summary": "Checkout database pool saturated", "description": "The pool is exhausted."}}
        firing = alertmanager.normalize_group({"alerts": [dict(alert, status="firing")]})["firing"][0]
        resolved = alertmanager.normalize_group({"alerts": [dict(alert, status="resolved", endsAt=app.now())]})["resolved"][0]
        self.assertEqual(firing["correlation_id"], resolved["correlation_id"])
        self.assertEqual(firing["severity"], "P1")
        self.assertEqual(firing["service_id"], "checkout")
        self.assertIn("ends_at", resolved)

    def test_rejects_unscoped_or_malformed_alerts(self):
        for payload in ({}, {"alerts": ["not-an-alert"]},
            {"alerts": [{"status": "firing", "fingerprint": "abcd", "startsAt": app.now(),
                "labels": {}, "annotations": {}}]}):
            with self.subTest(payload=payload), self.assertRaises(app.ApiError):
                alertmanager.normalize_group(payload)


class LokiAdapterTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "OPSPILOT_LOKI_URL": "https://logs.example.test",
            "OPSPILOT_LOKI_QUERIES": json.dumps({"log.db_acquire_timeout": "Connection acquisition timed out"}),
            "OPSPILOT_LOKI_TOKEN": "test-token",
        }, clear=False)
        self.environment.start()
        observed = datetime.now(timezone.utc) - timedelta(seconds=90)
        self.incident = {"id": "INC_test", "correlation_id": "corr_test",
            "created_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
        self.observed = observed

    def tearDown(self):
        self.environment.stop()

    def test_collects_service_scoped_matches_without_persisting_raw_log_text(self):
        def respond(request):
            self.assertEqual(request.url.path, "/loki/api/v1/query_range")
            self.assertEqual(request.headers["Authorization"], "Bearer test-token")
            query = request.url.params["query"]
            self.assertIn('{service_name="checkout"}', query)
            self.assertIn('"Connection acquisition timed out"', query)
            self.assertLessEqual(int(request.url.params["start"]), int(self.observed.timestamp() * 1_000_000_000))
            return httpx.Response(200, json={"status": "success", "data": {"result": [{
                "stream": {"service_name": "checkout"},
                "values": [[str(int(self.observed.timestamp() * 1_000_000_000)), "secret=do-not-store"]],
            }]}})

        records = loki.collect(self.incident, None, {"checkout", "postgres"}, transport=httpx.MockTransport(respond))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["signal_id"], "log.db_acquire_timeout")
        self.assertEqual(records[0]["service_id"], "checkout")
        self.assertEqual(records[0]["provenance"], "loki-http-api")
        self.assertNotIn("secret", json.dumps(records))

    def test_unsupported_signals_untrusted_urls_and_bad_responses_fail_closed(self):
        with patch.dict(os.environ, {"OPSPILOT_LOKI_URL": "http://logs.example.test"}):
            with self.assertRaises(app.ApiError) as error:
                loki.configuration()
        self.assertEqual(error.exception.code, "loki_configuration")
        with patch.dict(os.environ, {"OPSPILOT_LOKI_QUERIES": '{"trace.db_wait_high":"x"}'}):
            with self.assertRaises(app.ApiError):
                loki.configuration()
        for handler in (
            lambda request: httpx.Response(302),
            lambda request: httpx.Response(200, content=b" " * (loki.provider_http.MAX_RESPONSE + 1)),
            lambda request: httpx.Response(200, json={"status": "success", "data": {"result": [{
                "stream": {"service_name": "checkout"}, "values": [[str(index), "line"] for index in range(26)]
            }]}}),
        ):
            with self.subTest(response=handler):
                with self.assertRaises(app.ApiError) as error:
                    loki.collect(self.incident, None, {"checkout"}, transport=httpx.MockTransport(handler))
                self.assertEqual(error.exception.code, "loki_unavailable")


class TempoAdapterTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "OPSPILOT_TEMPO_URL": "https://traces.example.test",
            "OPSPILOT_TEMPO_QUERIES": json.dumps({"trace.db_wait_high": "span.http.response.status_code = 500"}),
            "OPSPILOT_TEMPO_TOKEN": "test-token",
        }, clear=False)
        self.environment.start()
        self.incident = {"id": "INC_test", "correlation_id": "corr_test",
            "created_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
        self.observed = datetime.now(timezone.utc) - timedelta(seconds=90)

    def tearDown(self):
        self.environment.stop()

    def test_collects_bounded_service_scoped_trace_matches(self):
        def respond(request):
            self.assertEqual(request.url.path, "/api/search")
            self.assertEqual(request.headers["Authorization"], "Bearer test-token")
            query = request.url.params["q"]
            self.assertIn('resource.service.name = "checkout"', query)
            self.assertIn("span.http.response.status_code = 500", query)
            self.assertLessEqual(int(request.url.params["start"]), int(self.observed.timestamp()))
            self.assertEqual(request.url.params["limit"], "25")
            return httpx.Response(200, json={"traces": [{
                "traceID": "a" * 31,
                "startTimeUnixNano": str(int(self.observed.timestamp() * 1_000_000_000)),
                "spanSet": {"spans": [{"durationNanos": "123456000"}]},
            }]})

        records = tempo.collect(self.incident, None, {"checkout", "postgres"}, transport=httpx.MockTransport(respond))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["signal_id"], "trace.db_wait_high")
        self.assertEqual(records[0]["trace_id"], "0" + "a" * 31)
        self.assertEqual(records[0]["provenance"], "tempo-search-api")
        self.assertIn("123.456 ms", records[0]["observation"])

    def test_rejects_zero_tempo_trace_id(self):
        with self.assertRaises(app.ApiError) as error:
            tempo.collect(self.incident, None, {"checkout"}, transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"traces": [{
                    "traceID": "0" * 32,
                    "startTimeUnixNano": str(int(self.observed.timestamp() * 1_000_000_000)),
                    "spanSet": {"spans": [{"durationNanos": "1"}]},
                }]})
            ))
        self.assertEqual(error.exception.code, "tempo_unavailable")

    def test_rejects_unsafe_query_and_out_of_scope_trace_ids(self):
        with patch.dict(os.environ, {"OPSPILOT_TEMPO_QUERIES": '{"trace.db_wait_high":"{} || true"}'}):
            with self.assertRaises(app.ApiError) as error:
                tempo.configuration()
        self.assertEqual(error.exception.code, "tempo_configuration")
        calls = []
        records = tempo.collect(self.incident, "catalog", {"checkout"},
            transport=httpx.MockTransport(lambda request: calls.append(request)))
        self.assertEqual(records, [])
        self.assertEqual(calls, [])

    def test_missing_tempo_span_duration_fails_closed(self):
        with self.assertRaises(app.ApiError) as error:
            tempo.collect(self.incident, None, {"checkout"}, transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"traces": [{
                    "traceID": "a" * 32,
                    "startTimeUnixNano": str(int(self.observed.timestamp() * 1_000_000_000)),
                    "spanSet": {"spans": []},
                }]})
            ))
        self.assertEqual(error.exception.code, "tempo_unavailable")


class PrometheusAdapterTests(unittest.TestCase):
    def test_queries_include_bounded_pre_alert_lookback(self):
        now = datetime.now(timezone.utc)
        observed = now - timedelta(seconds=90)
        incident = {"id": "INC_test", "correlation_id": "corr_test",
            "created_at": (now - timedelta(minutes=1)).isoformat()}
        with patch.dict(os.environ, {
            "OPSPILOT_PROMETHEUS_URL": "https://metrics.example.test",
            "OPSPILOT_PROMETHEUS_QUERIES": json.dumps({"metric.db_pool_saturated": "pool_utilization > 0.9"}),
            "OPSPILOT_PROMETHEUS_TOKEN": "test-token",
        }, clear=False):
            def respond(request):
                self.assertEqual(request.headers["Authorization"], "Bearer test-token")
                params = parse_qs(request.content.decode())
                self.assertLessEqual(float(params["start"][0]), observed.timestamp())
                return httpx.Response(200, json={"status": "success", "data": {"resultType": "matrix", "result": [{
                    "metric": {"service_id": "checkout"},
                    "values": [[str(observed.timestamp()), "0.97"]],
                }]}})

            records = prometheus.collect(incident, None, {"checkout"},
                transport=httpx.MockTransport(respond))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["provenance"], "prometheus-http-api")

if __name__ == "__main__":
    unittest.main()
