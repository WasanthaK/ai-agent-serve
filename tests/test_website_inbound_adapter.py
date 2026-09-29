import importlib
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from starlette.requests import Request

from inbound import NormalizedInboundMessage
from inbound_adapters import normalize_website_message


INBOUND_KEY = "inbound-" + "a" * 40
OPERATOR_KEY = "operator-" + "b" * 40
OPERATORS = [
    {
        "id": "wasantha",
        "key": OPERATOR_KEY,
        "permissions": ["read", "analyze", "reply", "decide", "tools"],
    }
]

with patch.dict(
    os.environ,
    {
        "OPENAI_API_KEY": "test-only-key",
        "AGENT_INBOUND_API_KEY": INBOUND_KEY,
        "AGENT_OPERATOR_CREDENTIALS": json.dumps(OPERATORS),
        "AGENT_INBOUND_SOURCE": "website",
    },
):
    api = importlib.import_module("app")


ANALYSIS = {
    "intent": "Request a quote",
    "category": "plumbing",
    "summary": "Leaking tap",
    "urgency": "normal",
    "next_action": "Arrange a plumber",
    "needs_human_review": False,
    "missing_information": [],
    "follow_up_questions": [],
}


def http_request():
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/webhook/quote-request",
            "headers": [],
        }
    )


def saved_request(request_id, message="My tap is leaking"):
    return {
        "id": request_id,
        "source": "website",
        "customer_name": "Test Customer",
        "message": message,
        "status": "ready",
        **ANALYSIS,
    }


class WebsiteInboundAdapterTests(unittest.TestCase):
    def test_adapter_uses_authenticated_channel_and_message_text(self):
        normalized = normalize_website_message(
            authenticated_channel="website",
            text="My tap is leaking",
        )

        self.assertIsInstance(normalized, NormalizedInboundMessage)
        self.assertEqual(normalized.channel, "website")
        self.assertEqual(normalized.text, "My tap is leaking")
        self.assertIsNone(normalized.sender)
        self.assertEqual(normalized.attachments, [])

    def test_source_mismatch_is_rejected_before_normalization(self):
        request = api.QuoteWebhookRequest(
            source="email",
            customer_name="Test Customer",
            message="My tap is leaking",
        )

        with (
            patch.object(api, "normalize_website_message") as normalize,
            patch.object(api, "audit_denial") as audit,
        ):
            with self.assertRaises(HTTPException) as raised:
                api.quote_webhook(
                    request,
                    http_request(),
                    idempotency_key=None,
                    source="website",
                )

        self.assertEqual(raised.exception.status_code, 403)
        normalize.assert_not_called()
        audit.assert_called_once()

    def test_webhook_downstream_path_consumes_normalized_message(self):
        request_id = uuid4()
        request = api.QuoteWebhookRequest(
            source="website",
            customer_name="Test Customer",
            message="Original website text",
        )
        normalized = NormalizedInboundMessage(
            channel="website",
            text="Normalized website text",
        )
        stored = saved_request(request_id, message=normalized.text)

        with (
            patch.object(
                api,
                "normalize_website_message",
                return_value=normalized,
            ) as normalize,
            patch.object(
                api,
                "analyze_quote_request",
                return_value=dict(ANALYSIS),
            ) as analyze,
            patch.object(api, "save_request", return_value=request_id) as save,
            patch.object(api, "get_request", return_value=stored),
        ):
            response = api.quote_webhook(
                request,
                http_request(),
                idempotency_key=None,
                source="website",
            )

        normalize.assert_called_once_with(
            authenticated_channel="website",
            text="Original website text",
        )
        analyze.assert_called_once_with(
            message="Normalized website text",
            source="website",
            customer_name="Test Customer",
        )
        self.assertEqual(save.call_args.args[0], "website")
        self.assertEqual(save.call_args.args[1], "Test Customer")
        self.assertEqual(save.call_args.args[2], "Normalized website text")
        self.assertEqual(response["source"], "website")
        self.assertEqual(response["customer_name"], "Test Customer")
        self.assertEqual(response["workflow_status"], "ready")
        self.assertEqual(response["analysis"], ANALYSIS)

    def test_idempotency_identity_remains_source_customer_and_text(self):
        request_id = uuid4()
        request = api.QuoteWebhookRequest(
            source="website",
            customer_name="Test Customer",
            message="My tap is leaking",
        )
        normalized = NormalizedInboundMessage(
            channel="website",
            text="My tap is leaking",
        )

        with (
            patch.object(
                api,
                "normalize_website_message",
                return_value=normalized,
            ),
            patch.object(
                api,
                "hash_webhook_payload",
                return_value="payload-hash",
            ) as payload_hash,
            patch.object(
                api,
                "reserve_webhook_delivery",
                return_value={"action": "processing", "request_id": request_id},
            ) as reserve,
        ):
            with self.assertRaises(HTTPException) as raised:
                api.quote_webhook(
                    request,
                    http_request(),
                    idempotency_key="delivery-123",
                    source="website",
                )

        self.assertEqual(raised.exception.status_code, 409)
        payload_hash.assert_called_once_with(
            "website",
            "Test Customer",
            "My tap is leaking",
        )
        self.assertEqual(reserve.call_args.args[0], "website")
        self.assertEqual(reserve.call_args.args[2], "payload-hash")


if __name__ == "__main__":
    unittest.main()
