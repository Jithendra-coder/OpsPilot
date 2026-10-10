import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx

import app
from backend import prometheus


class PrometheusAdapterTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "OPSPILOT_PROMETHEUS_URL": "https://metrics.example.test",
            "OPSPILOT_PROMETHEUS_QUERIES": json.dumps({"metric.db_pool_saturated": "checkout_db_pool_utilization > 0.9"}),
            "OPSPILOT_PROMETHEUS_TOKEN": "test-token",
        }, clear=False)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()

    def test_collect_maps_bounded_prometheus_samples_with_scope_and_provenance(self):
        observed = datetime.now(timezone.utc) - timedelta(seconds=30)

        def respond(request):
            self.assertEqual(request.url.path, "/api/v1/query_range")
            self.assertEqual(request.headers["Authorization"], "Bearer test-token")
            self.assertEqual(parse_qs(request.content.decode())["limit"], ["1"])
            return httpx.Response(200, json={"status": "success", "data": {"resultType": "matrix", "result": [{
                "metric": {"service_id": "checkout"}, "values": [[observed.timestamp(), "0.97"]]}]}})

        incident = {"id": "INC_test", "correlation_id": "corr_test",
            "created_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
        records = prometheus.collect(incident, None, {"checkout", "postgres"},
            transport=httpx.MockTransport(respond))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["signal_id"], "metric.db_pool_saturated")
        self.assertEqual(records[0]["service_id"], "checkout")
        self.assertEqual(records[0]["provenance"], "prometheus-http-api")
        self.assertEqual(records[0]["observation"], "Configured PromQL signal matched at value 0.97")

    def test_rejects_nonlocal_http_and_unsupported_signal_queries(self):
        with patch.dict(os.environ, {"OPSPILOT_PROMETHEUS_URL": "http://metrics.example.test"}):
            with self.assertRaises(app.ApiError) as error:
                prometheus.configuration()
        self.assertEqual(error.exception.code, "prometheus_configuration")
        with patch.dict(os.environ, {"OPSPILOT_PROMETHEUS_QUERIES": '{"log.db_acquire_timeout":"up"}'}):
            with self.assertRaises(app.ApiError):
                prometheus.configuration()

    def test_provider_errors_and_oversized_responses_fail_closed(self):
        incident = {"id": "INC_test", "correlation_id": "corr_test",
            "created_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
        for handler in (
            lambda request: httpx.Response(302),
            lambda request: httpx.Response(200, content=b" " * (prometheus.MAX_RESPONSE + 1)),
        ):
            with self.subTest(response=handler):
                with self.assertRaises(app.ApiError) as error:
                    prometheus.collect(incident, None, {"checkout"}, transport=httpx.MockTransport(handler))
                self.assertEqual(error.exception.code, "prometheus_unavailable")

    def test_ignores_wrong_service_labels_and_rejects_malformed_query_results(self):
        incident = {"id": "INC_test", "correlation_id": "corr_test",
            "created_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
        wrong_service = lambda request: httpx.Response(200, json={"status": "success", "data": {
            "resultType": "matrix", "result": [{"metric": {"service_id": "catalog"}, "values": []}]}})
        self.assertEqual(prometheus.collect(incident, None, {"checkout"}, transport=httpx.MockTransport(wrong_service)), [])
        malformed = lambda request: httpx.Response(200, json={"status": "success", "data": {"resultType": "vector"}})
        with self.assertRaises(app.ApiError) as error:
            prometheus.collect(incident, None, {"checkout"}, transport=httpx.MockTransport(malformed))
        self.assertEqual(error.exception.code, "prometheus_unavailable")


if __name__ == "__main__":
    unittest.main()
