import json
import os
import unittest
from unittest.mock import patch

from backend.llm import rank_hypotheses


class FakeResponse:
    status = 200
    headers = {"Content-Length": "0"}

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit):
        return self.payload[:limit]


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.request = None
        self.timeout = None

    def open(self, request, timeout):
        self.request, self.timeout = request, timeout
        return self.response


class OptionalLLMTests(unittest.TestCase):
    def test_review_is_https_opt_in_bounded_and_limited_to_candidate_ordering(self):
        answer = {"order": ["db_pool"], "rationale": "Pool saturation appears in the supplied metrics.", "missing_evidence": ["logs", "secrets"]}
        content = json.dumps({"choices": [{"message": {"content": json.dumps(answer)}}]}).encode()
        opener = FakeOpener(FakeResponse(content))
        environment = {"OPSPILOT_LLM_DATA_CONSENT": "true", "OPSPILOT_LLM_API_KEY": "local-test-key",
            "OPSPILOT_LLM_MODEL": "test-model", "OPSPILOT_LLM_BASE_URL": "https://provider.example/v1"}
        candidates = [{"cause_id": "db_pool", "component": "checkout", "title": "Pool saturation", "evidence_ids": ["ev1"]},
            {"cause_id": "cache_unavailable", "component": "catalog", "title": "Cache unavailable", "evidence_ids": ["ev2"]}]
        evidence = [{"id": "ev1", "kind": "logs", "source": "checkout", "observation": "password: sensitive-value", "severity": "error"}]
        with patch.dict(os.environ, environment, clear=True), patch("backend.llm.urllib.request.build_opener", return_value=opener):
            result = rank_hypotheses(candidates, evidence)
        self.assertEqual(result["status"], "used")
        self.assertEqual(result["order"], ["db_pool", "cache_unavailable"])
        self.assertEqual(result["missing_evidence"], ["logs"])
        self.assertEqual(opener.timeout, 8)
        sent = json.loads(opener.request.data)["messages"][1]["content"]
        self.assertNotIn("sensitive-value", sent)
        self.assertIn("[REDACTED]", sent)

    def test_non_https_or_unconsented_provider_stays_disabled(self):
        environment = {"OPSPILOT_LLM_DATA_CONSENT": "true", "OPSPILOT_LLM_API_KEY": "local-test-key",
            "OPSPILOT_LLM_MODEL": "test-model", "OPSPILOT_LLM_BASE_URL": "http://localhost/v1"}
        candidate = [{"cause_id": "db_pool", "component": "checkout", "title": "Pool saturation", "evidence_ids": []}]
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(rank_hypotheses(candidate, [])["status"], "disabled")


if __name__ == "__main__":
    unittest.main()
