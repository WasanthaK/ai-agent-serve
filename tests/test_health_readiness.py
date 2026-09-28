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
    {
        "id": "wasantha",
        "key": OPERATOR_KEY,
        "permissions": ["read", "analyze", "reply", "decide", "tools"],
    },
    {
        "id": "viewer",
        "key": VIEWER_KEY,
        "permissions": ["read"],
    },
]

with patch.dict(os.environ, {
    "OPENAI_API_KEY": "test-only-key",
    "AGENT_INBOUND_API_KEY": INBOUND_KEY,
    "AGENT_OPERATOR_CREDENTIALS": json.dumps(OPERATORS),
    "AGENT_INBOUND_SOURCE": "website",
}):
    api = importlib.import_module("app")


class HealthReadinessTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)

    def test_liveness_is_public_and_dependency_free(self):
        with patch.object(api, "database_ready") as database_ready:
            response = self.client.get("/health/live")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "status": "alive",
            "service": "agent-server",
        })
        database_ready.assert_not_called()

    def test_readiness_reports_database_ready(self):
        with patch.object(api, "database_ready", return_value=True):
            response = self.client.get("/health/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "status": "ready",
            "service": "agent-server",
            "dependencies": {
                "database": "ready",
            },
        })

    def test_readiness_fails_closed_without_error_details(self):
        with patch.object(api, "database_ready", return_value=False):
            response = self.client.get("/health/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {
            "detail": "Service is not ready",
        })
        self.assertNotIn("postgres", response.text.lower())
        self.assertNotIn("password", response.text.lower())


if __name__ == "__main__":
    unittest.main()
