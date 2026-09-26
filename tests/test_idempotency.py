import importlib
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from starlette.requests import Request


INBOUND_KEY = "inbound-" + "a" * 40
OPERATOR_KEY = "operator-" + "b" * 40
OPERATORS = [
    {
        "id": "test-operator",
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
    idempotency = importlib.import_module("idempotency")


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


def saved_request(request_id):
    return {
        "id": request_id,
        "source": "website",
        "customer_name": "Test Customer",
        "message": "My tap is leaking",
        "status": "ready",
        **ANALYSIS,
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


class IdempotencyHashTests(unittest.TestCase):
    def test_key_and_payload_hashes_are_deterministic_and_do_not_store_raw_values(self):
        key = "delivery-secret-123"
        key_hash = idempotency.hash_idempotency_key(key)
        payload_hash = idempotency.hash_webhook_payload(
            "website", "Test Customer", "My tap is leaking"
        )

        self.assertEqual(key_hash, idempotency.hash_idempotency_key(key))
        self.assertEqual(
            payload_hash,
            idempotency.hash_webhook_payload(
                "website", "Test Customer", "My tap is leaking"
            ),
        )
        self.assertNotIn(key, key_hash)
        self.assertEqual(len(key_hash), 64)
        self.assertEqual(len(payload_hash), 64)


class QuoteWebhookIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.request = api.QuoteWebhookRequest(
            source="website",
            customer_name="Test Customer",
            message="My tap is leaking",
        )

    def test_first_delivery_uses_reserved_request_id_and_completes(self):
        request_id = uuid4()
        stored = saved_request(request_id)

        with (
            patch.object(
                api,
                "reserve_webhook_delivery",
                return_value={"action": "process", "request_id": request_id},
            ),
            patch.object(api, "analyze_quote_request", return_value=dict(ANALYSIS)) as analyze,
            patch.object(api, "save_request", return_value=request_id) as save,
            patch.object(api, "get_request", return_value=stored),
            patch.object(api, "complete_webhook_delivery") as complete,
            patch.object(api, "release_webhook_delivery") as release,
        ):
            response = api.quote_webhook(
                self.request,
                http_request(),
                idempotency_key="delivery-123",
                source="website",
            )

        self.assertEqual(response["request_id"], request_id)
        analyze.assert_called_once()
        self.assertEqual(save.call_args.kwargs["request_id"], request_id)
        complete.assert_called_once()
        release.assert_not_called()

    def test_completed_replay_returns_original_without_model_or_insert(self):
        request_id = uuid4()
        stored = saved_request(request_id)

        with (
            patch.object(
                api,
                "reserve_webhook_delivery",
                return_value={"action": "completed", "request_id": request_id},
            ),
            patch.object(api, "analyze_quote_request") as analyze,
            patch.object(api, "save_request") as save,
            patch.object(api, "get_request", return_value=stored),
        ):
            response = api.quote_webhook(
                self.request,
                http_request(),
                idempotency_key="delivery-123",
                source="website",
            )

        self.assertEqual(response["request_id"], request_id)
        self.assertEqual(response["workflow_status"], "ready")
        analyze.assert_not_called()
        save.assert_not_called()

    def test_key_reuse_with_different_payload_is_rejected(self):
        with patch.object(
            api,
            "reserve_webhook_delivery",
            return_value={"action": "conflict", "request_id": uuid4()},
        ):
            with self.assertRaises(HTTPException) as raised:
                api.quote_webhook(
                    self.request,
                    http_request(),
                    idempotency_key="delivery-123",
                    source="website",
                )

        self.assertEqual(raised.exception.status_code, 409)

    def test_inflight_duplicate_is_rejected_with_retry_after(self):
        with patch.object(
            api,
            "reserve_webhook_delivery",
            return_value={"action": "processing", "request_id": uuid4()},
        ):
            with self.assertRaises(HTTPException) as raised:
                api.quote_webhook(
                    self.request,
                    http_request(),
                    idempotency_key="delivery-123",
                    source="website",
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.headers["Retry-After"], "2")

    def test_analysis_failure_releases_reservation_for_retry(self):
        request_id = uuid4()

        with (
            patch.object(
                api,
                "reserve_webhook_delivery",
                return_value={"action": "process", "request_id": request_id},
            ),
            patch.object(
                api,
                "analyze_quote_request",
                side_effect=HTTPException(status_code=502, detail="temporary"),
            ),
            patch.object(api, "release_webhook_delivery") as release,
        ):
            with self.assertRaises(HTTPException):
                api.quote_webhook(
                    self.request,
                    http_request(),
                    idempotency_key="delivery-123",
                    source="website",
                )

        release.assert_called_once()
        self.assertEqual(release.call_args.args[2], request_id)

    def test_missing_idempotency_key_preserves_existing_behavior(self):
        request_id = uuid4()
        stored = saved_request(request_id)

        with (
            patch.object(api, "reserve_webhook_delivery") as reserve,
            patch.object(api, "analyze_quote_request", return_value=dict(ANALYSIS)),
            patch.object(api, "save_request", return_value=request_id) as save,
            patch.object(api, "get_request", return_value=stored),
        ):
            response = api.quote_webhook(
                self.request,
                http_request(),
                idempotency_key=None,
                source="website",
            )

        self.assertEqual(response["request_id"], request_id)
        reserve.assert_not_called()
        self.assertIsNone(save.call_args.kwargs["request_id"])


if __name__ == "__main__":
    unittest.main()
