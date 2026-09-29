import base64
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sendgrid_routes import build_sendgrid_router


class SendGridRouteTests(unittest.TestCase):
    def setUp(self):
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        public_der = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.public_key_b64 = base64.b64encode(public_der).decode("ascii")

    def _multipart_body(self, boundary):
        parts = [
            ("from", "Example Customer <customer@example.com>"),
            ("subject", "Leaking tap"),
            ("text", "Please quote this repair."),
            (
                "headers",
                "Message-ID: <route-test@example.com>\n"
                "Date: Tue, 29 Sep 2026 08:00:00 +0000\n",
            ),
        ]
        chunks = []
        for name, value in parts:
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    (
                        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                    ).encode(),
                    value.encode(),
                    b"\r\n",
                ]
            )
        chunks.append(f"--{boundary}--\r\n".encode())
        return b"".join(chunks)

    def _signature(self, timestamp, raw_body):
        signature = self.private_key.sign(
            timestamp.encode("utf-8") + raw_body,
            ec.ECDSA(hashes.SHA256()),
        )
        return base64.b64encode(signature).decode("ascii")

    def test_verified_message_is_persisted_before_analysis_and_reuses_inbound_id(self):
        request_id = uuid4()
        calls = []
        saved_requests = {}

        def fake_persist(normalized):
            calls.append(("persist", normalized.external_message_id))
            return {
                "action": "created",
                "message": {
                    "id": request_id,
                    "linked_request_id": None,
                },
            }

        def fake_analyze(message, source, customer_name):
            calls.append(("analyze", source))
            return {
                "intent": "Request a quote",
                "category": "Plumbing",
                "summary": "Leaking tap",
                "urgency": "normal",
                "next_action": "Prepare quote",
                "needs_human_review": False,
                "missing_information": [],
                "follow_up_questions": [],
            }

        def fake_save_request(
            source,
            customer_name,
            message,
            result,
            request_id=None,
            skill_versions=None,
        ):
            calls.append(("save_request", request_id))
            saved_requests[request_id] = {
                "id": request_id,
                "status": "ready",
            }
            return request_id

        def fake_get_request(value):
            return saved_requests.get(value)

        app = FastAPI()
        app.include_router(
            build_sendgrid_router(
                analyze_quote_request=fake_analyze,
                save_request=fake_save_request,
                get_request=fake_get_request,
                skill_versions={"request_intake": "1.0.0"},
            )
        )

        boundary = "sendgrid-route-test"
        raw_body = self._multipart_body(boundary)
        timestamp = "1790670000"
        signature = self._signature(timestamp, raw_body)

        with (
            patch.dict(
                os.environ,
                {"SENDGRID_INBOUND_PUBLIC_KEY": self.public_key_b64},
                clear=False,
            ),
            patch("sendgrid_routes.save_inbound_message", side_effect=fake_persist),
            patch("sendgrid_routes.link_inbound_message_to_request") as link_mock,
        ):
            response = TestClient(app).post(
                "/webhook/sendgrid/inbound",
                content=raw_body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "X-Twilio-Email-Event-Webhook-Signature": signature,
                    "X-Twilio-Email-Event-Webhook-Timestamp": timestamp,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["request_id"], str(request_id))
        self.assertEqual(payload["workflow_status"], "ready")
        self.assertEqual(calls[0][0], "persist")
        self.assertEqual(calls[1][0], "analyze")
        self.assertEqual(calls[2], ("save_request", request_id))
        link_mock.assert_called_once_with(request_id, request_id)

    def test_invalid_signature_is_rejected_before_persistence(self):
        app = FastAPI()
        app.include_router(
            build_sendgrid_router(
                analyze_quote_request=lambda **kwargs: None,
                save_request=lambda *args, **kwargs: None,
                get_request=lambda request_id: None,
                skill_versions={},
            )
        )

        boundary = "sendgrid-route-test"
        raw_body = self._multipart_body(boundary)

        with (
            patch.dict(
                os.environ,
                {"SENDGRID_INBOUND_PUBLIC_KEY": self.public_key_b64},
                clear=False,
            ),
            patch("sendgrid_routes.save_inbound_message") as persist_mock,
        ):
            response = TestClient(app).post(
                "/webhook/sendgrid/inbound",
                content=raw_body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "X-Twilio-Email-Event-Webhook-Signature": "invalid",
                    "X-Twilio-Email-Event-Webhook-Timestamp": "1790670000",
                },
            )

        self.assertEqual(response.status_code, 401)
        persist_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
