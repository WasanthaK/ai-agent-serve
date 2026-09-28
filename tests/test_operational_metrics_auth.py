import importlib
import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


INBOUND_KEY = "inbound-" + "a" * 40
OPERATOR_KEY = "operator-" + "b" * 40
VIEWER_KEY = "viewer-" + "c" * 40
OPERATORS = [
    {"id": "wasantha", "key": OPERATOR_KEY,
     "permissions": ["read", "analyze", "reply", "decide", "tools"]},
    {"id": "viewer", "key": VIEWER_KEY, "permissions": ["read"]},
]

with patch.dict(os.environ, {
    "OPENAI_API_KEY": "test-only-key",
    "AGENT_INBOUND_API_KEY": INBOUND_KEY,
    "AGENT_OPERATOR_CREDENTIALS": json.dumps(OPERATORS),
    "AGENT_INBOUND_SOURCE": "website",
}):
    api = importlib.import_module("app")


class OperationalMetricsAuthorizationTests(unittest.TestCase):
    def test_metrics_endpoint_requires_operator_read_permission(self):
        client = TestClient(api.app)

        missing = client.get("/metrics/operational")
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(missing.json(), {"detail": "Invalid API credentials"})

        wrong_role = client.get(
            "/metrics/operational",
            headers={"X-API-Key": INBOUND_KEY},
        )
        self.assertEqual(wrong_role.status_code, 401)
        self.assertEqual(wrong_role.json(), {"detail": "Invalid API credentials"})

        allowed = client.get(
            "/metrics/operational",
            headers={"X-API-Key": VIEWER_KEY},
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertIn("process", allowed.json())
        self.assertIn("http", allowed.json())


if __name__ == "__main__":
    unittest.main()
