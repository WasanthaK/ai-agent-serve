import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from quixo_whatsapp_routes import build_quixo_whatsapp_router


class QuixoWhatsAppRouteTests(unittest.TestCase):
    def test_authenticated_message_persists_before_analysis(self):
        request_id = uuid4()
        calls = []
        saved_requests = {}

        def authenticated_channel():
            return "whatsapp"

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
            calls.append(("analyze", source, customer_name))
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
            build_quixo_whatsapp_router(
                analyze_quote_request=fake_analyze,
                save_request=fake_save_request,
                get_request=fake_get_request,
                skill_versions={"request_intake": "1.0.0"},
                channel_dependency=authenticated_channel,
            )
        )

        payload = {
            "sender_external_id": "61412345678",
            "sender_address": "+61412345678",
            "sender_display_name": "Example Customer",
            "body_text": "Please quote a leaking kitchen tap.",
            "external_message_id": "SM33333333333333333333333333333333",
            "external_conversation_id": "conversation-123",
            "attachments": [],
        }

        with (
            patch("quixo_whatsapp_routes.save_inbound_message", side_effect=fake_persist),
            patch("quixo_whatsapp_routes.link_inbound_message_to_request") as link_mock,
        ):
            response = TestClient(app).post(
                "/webhook/whatsapp/inbound",
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "accepted")
        self.assertEqual(body["request_id"], str(request_id))
        self.assertEqual(body["workflow_status"], "ready")
        self.assertEqual(calls[0][0], "persist")
        self.assertEqual(calls[1][0], "analyze")
        self.assertEqual(calls[2], ("save_request", request_id))
        link_mock.assert_called_once_with(request_id, request_id)

    def test_wrong_channel_dependency_is_rejected_by_normalizer(self):
        def wrong_channel():
            return "email"

        app = FastAPI()
        app.include_router(
            build_quixo_whatsapp_router(
                analyze_quote_request=lambda **kwargs: None,
                save_request=lambda *args, **kwargs: None,
                get_request=lambda request_id: None,
                skill_versions={},
                channel_dependency=wrong_channel,
            )
        )

        payload = {
            "sender_external_id": "61412345678",
            "body_text": "Please quote this job.",
            "external_message_id": "SM33333333333333333333333333333333",
        }

        with patch("quixo_whatsapp_routes.save_inbound_message") as persist_mock:
            response = TestClient(app, raise_server_exceptions=False).post(
                "/webhook/whatsapp/inbound",
                json=payload,
            )

        self.assertEqual(response.status_code, 500)
        persist_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
