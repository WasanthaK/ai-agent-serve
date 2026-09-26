import json
import unittest
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from observability import (
    StructuredRequestLoggingMiddleware,
    correlation_exception_handler,
)


class ObservabilityTests(unittest.TestCase):
    def make_client(self, raise_server_exceptions=True):
        app = FastAPI()
        app.add_middleware(StructuredRequestLoggingMiddleware)
        app.add_exception_handler(Exception, correlation_exception_handler)

        @app.post("/probe")
        async def probe(request: Request):
            await request.body()
            return {"ok": True}

        @app.get("/explode")
        async def explode():
            raise ValueError("sensitive internal detail")

        return TestClient(
            app,
            raise_server_exceptions=raise_server_exceptions,
        )

    def test_response_has_server_generated_correlation_id_and_json_log(self):
        client = self.make_client()
        secret = "customer-secret-text"

        with self.assertLogs("agent.requests", level="INFO") as captured:
            response = client.post(
                "/probe?token=must-not-log",
                headers={"X-API-Key": "must-not-log-key"},
                content=secret,
            )

        self.assertEqual(response.status_code, 200)
        correlation_id = response.headers["X-Correlation-ID"]
        UUID(correlation_id)

        payload = json.loads(captured.output[-1].split(":", 2)[-1])
        self.assertEqual(payload["event"], "request_completed")
        self.assertEqual(payload["correlation_id"], correlation_id)
        self.assertEqual(payload["method"], "POST")
        self.assertEqual(payload["route"], "/probe")
        self.assertEqual(payload["status_code"], 200)
        self.assertIn("duration_ms", payload)

        rendered = captured.output[-1]
        self.assertNotIn(secret, rendered)
        self.assertNotIn("must-not-log", rendered)
        self.assertNotIn("X-API-Key", rendered)

    def test_failure_response_and_log_share_correlation_id_without_message(self):
        client = self.make_client(raise_server_exceptions=False)

        with self.assertLogs("agent.requests", level="INFO") as captured:
            response = client.get("/explode")

        self.assertEqual(response.status_code, 500)
        correlation_id = response.headers["X-Correlation-ID"]
        UUID(correlation_id)

        payload = json.loads(captured.output[-1].split(":", 2)[-1])
        self.assertEqual(payload["event"], "request_failed")
        self.assertEqual(payload["correlation_id"], correlation_id)
        self.assertEqual(payload["route"], "/explode")
        self.assertEqual(payload["error_type"], "ValueError")
        self.assertNotIn("sensitive internal detail", captured.output[-1])
        self.assertNotIn("sensitive internal detail", response.text)


if __name__ == "__main__":
    unittest.main()
