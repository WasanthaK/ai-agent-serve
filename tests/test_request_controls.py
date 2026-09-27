import json
import os
import unittest
from unittest.mock import patch
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import observability
from observability import StructuredRequestLoggingMiddleware
from request_controls import RequestBodyLimitMiddleware, load_max_request_bytes


class RequestControlTests(unittest.TestCase):
    def test_load_default_limit(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(load_max_request_bytes(), 65536)

    def test_invalid_limit_configuration_is_rejected(self):
        for value in ("not-an-int", "0", "-1", "10485761"):
            with self.subTest(value=value), patch.dict(
                os.environ,
                {"AGENT_MAX_REQUEST_BYTES": value},
                clear=True,
            ):
                with self.assertRaises(RuntimeError):
                    load_max_request_bytes()

    def test_exact_content_length_limit_is_accepted(self):
        app = FastAPI()
        app.add_middleware(RequestBodyLimitMiddleware, max_bytes=5)

        @app.post("/probe")
        async def probe(request: Request):
            body = await request.body()
            return {"size": len(body)}

        response = TestClient(app).post("/probe", content=b"12345")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"size": 5})

    def test_content_length_over_limit_is_rejected_before_endpoint(self):
        called = False
        app = FastAPI()
        app.add_middleware(RequestBodyLimitMiddleware, max_bytes=5)

        @app.post("/probe")
        async def probe():
            nonlocal called
            called = True
            return {"ok": True}

        response = TestClient(app).post("/probe", content=b"123456")
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json(), {"detail": "Request body too large"})
        self.assertFalse(called)

    def test_rejection_keeps_server_correlation_id_and_log(self):
        called = False
        app = FastAPI()

        with patch.object(observability, "MAX_REQUEST_BYTES", 5):
            app.add_middleware(StructuredRequestLoggingMiddleware)

            @app.post("/probe")
            async def probe():
                nonlocal called
                called = True
                return {"ok": True}

            client = TestClient(app)
            with self.assertLogs("agent.requests", level="INFO") as captured:
                response = client.post("/probe", content=b"123456")

        self.assertEqual(response.status_code, 413)
        correlation_id = response.headers["X-Correlation-ID"]
        UUID(correlation_id)
        self.assertFalse(called)

        payload = json.loads(captured.output[-1].split(":", 2)[-1])
        self.assertEqual(payload["event"], "request_completed")
        self.assertEqual(payload["correlation_id"], correlation_id)
        self.assertEqual(payload["status_code"], 413)


class StreamingRequestControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_chunked_body_cannot_bypass_limit(self):
        called = False

        async def downstream(scope, receive, send):
            nonlocal called
            called = True

        middleware = RequestBodyLimitMiddleware(downstream, max_bytes=5)
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/probe",
            "headers": [],
        }
        incoming = iter([
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"456", "more_body": False},
        ])
        sent = []

        async def receive():
            return next(incoming)

        async def send(message):
            sent.append(message)

        await middleware(scope, receive, send)

        self.assertFalse(called)
        start = next(message for message in sent if message["type"] == "http.response.start")
        self.assertEqual(start["status"], 413)


if __name__ == "__main__":
    unittest.main()
