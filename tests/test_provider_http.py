from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.provider_http import endpoint


class ProviderEndpointTests(unittest.TestCase):
    def test_http_requires_loopback_or_explicit_internal_host_allowlist(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(endpoint("TEST_URL", "/api"))
        with patch.dict(os.environ, {"TEST_URL": "http://127.0.0.1:9090"}, clear=True):
            self.assertEqual(endpoint("TEST_URL", "/api"), "http://127.0.0.1:9090/api")
        with patch.dict(os.environ, {"TEST_URL": "http://prometheus:9090", "OPSPILOT_PROVIDER_HTTP_HOSTS": "prometheus,loki"}, clear=True):
            self.assertEqual(endpoint("TEST_URL", "/api"), "http://prometheus:9090/api")
        with patch.dict(os.environ, {"TEST_URL": "http://other-service:9090", "OPSPILOT_PROVIDER_HTTP_HOSTS": "prometheus,loki"}, clear=True):
            with self.assertRaises(ValueError):
                endpoint("TEST_URL", "/api")

    def test_host_allowlist_does_not_relax_other_url_validation(self):
        with patch.dict(os.environ, {"TEST_URL": "http://prometheus:9090/?token=bad", "OPSPILOT_PROVIDER_HTTP_HOSTS": "prometheus"}, clear=True):
            with self.assertRaises(ValueError):
                endpoint("TEST_URL", "/api")


if __name__ == "__main__":
    unittest.main()
