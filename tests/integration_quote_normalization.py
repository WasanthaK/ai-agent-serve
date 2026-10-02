import unittest
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from db import get_connection, get_request_events, save_request
from provider_directory import (
    add_provider_coverage_area,
    add_provider_service_capability,
    create_provider,
    set_provider_availability,
    set_provider_compliance,
)
from provider_selection import select_providers_for_request
from quote_normalization import (
    QuoteNormalizationConflictError,
    QuoteNormalizationStateError,
    get_normalized_quote,
    normalize_structured_quote,
)
from rfq_delivery import authorize_rfq_delivery, confirm_rfq_delivery
from rfq_handoff import prepare_rfq_handoff
from rfq_response import ingest_rfq_response


def ready_analysis():
    return {
        "intent": "Request a quote",
        "category": "plumbing",
        "summary": "Replace leaking kitchen tap",
        "urgency": "normal",
        "next_action": "Route to providers",
        "needs_human_review": False,
        "missing_information": [],
        "follow_up_questions": [],
    }


class QuoteNormalizationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.request_ids = []
        self.provider_ids = []

    def tearDown(self):
        with get_connection() as conn:
            with conn.cursor() as cur:
                if self.request_ids:
                    cur.execute(
                        "DELETE FROM agent_requests WHERE id = ANY(%s)",
                        (self.request_ids,),
                    )
                if self.provider_ids:
                    cur.execute(
                        "DELETE FROM providers WHERE id = ANY(%s)",
                        (self.provider_ids,),
                    )

    def create_delivered_handoff(self):
        request_id = save_request(
            "website",
            "CI Customer",
            "Need plumbing work",
            ready_analysis(),
        )
        self.request_ids.append(request_id)

        provider_id = uuid4()
        self.provider_ids.append(provider_id)
        create_provider(
            "CI Normalized Quote Provider",
            approval_status="approved",
            provider_id=provider_id,
        )
        add_provider_service_capability(provider_id, "plumbing")
        add_provider_coverage_area(provider_id, "bn:brunei-muara")
        set_provider_availability(provider_id, "available")
        set_provider_compliance(provider_id, "compliant")

        select_providers_for_request(
            request_id,
            "plumbing",
            "bn:brunei-muara",
            [provider_id],
            actor="operator:ci",
        )
        rfq = prepare_rfq_handoff(request_id, actor="operator:ci")
        handoff_id = UUID(rfq["provider_handoffs"][0]["handoff_id"])

        authorize_rfq_delivery(request_id, handoff_id, actor="operator:ci")
        confirm_rfq_delivery(
            request_id,
            handoff_id,
            datetime.now(timezone.utc) + timedelta(hours=24),
            actor="operator:ci",
        )
        return request_id, provider_id, handoff_id

    def test_quote_response_normalizes_once_and_is_retrievable(self):
        request_id, provider_id, handoff_id = self.create_delivered_handoff()
        responded_at = datetime.now(timezone.utc)
        response = ingest_rfq_response(
            request_id,
            handoff_id,
            "quote",
            responded_at,
            actor="operator:ci",
        )

        expires_at = datetime.now(timezone.utc) + timedelta(days=14)
        first = normalize_structured_quote(
            request_id,
            handoff_id,
            amount_minor=125000,
            currency="aud",
            scope_summary="Supply and replace leaking kitchen tap.",
            exclusions=["Wall repairs"],
            terms=["50% deposit before work"],
            available_from=date(2026, 10, 10),
            estimated_duration_days=1,
            validity_expires_at=expires_at,
            actor="operator:ci",
        )

        self.assertEqual(first["provider_id"], str(provider_id))
        self.assertEqual(first["response_event_id"], response["response_id"])
        self.assertEqual(first["currency"], "AUD")
        self.assertEqual(first["amount_minor"], 125000)
        self.assertFalse(first["evaluated"])
        self.assertFalse(first["selected"])

        retry = normalize_structured_quote(
            request_id,
            handoff_id,
            amount_minor=125000,
            currency="AUD",
            scope_summary="Supply and replace leaking kitchen tap.",
            exclusions=["Wall repairs"],
            terms=["50% deposit before work"],
            available_from=date(2026, 10, 10),
            estimated_duration_days=1,
            validity_expires_at=expires_at,
            actor="operator:ci",
        )
        self.assertEqual(
            retry["normalized_quote_id"],
            first["normalized_quote_id"],
        )

        persisted = get_normalized_quote(request_id, handoff_id)
        self.assertEqual(
            persisted["normalized_quote_id"],
            first["normalized_quote_id"],
        )

        with self.assertRaises(QuoteNormalizationConflictError):
            normalize_structured_quote(
                request_id,
                handoff_id,
                amount_minor=130000,
                currency="AUD",
                scope_summary="Different amount",
                actor="operator:ci",
            )

        events = get_request_events(request_id)
        normalized = [
            event for event in events
            if event["event_type"] == "normalized_quote_recorded"
        ]
        self.assertEqual(len(normalized), 1)

    def test_decline_response_cannot_be_normalized_as_quote(self):
        request_id, _provider_id, handoff_id = self.create_delivered_handoff()
        ingest_rfq_response(
            request_id,
            handoff_id,
            "decline",
            datetime.now(timezone.utc),
            actor="operator:ci",
        )

        with self.assertRaises(QuoteNormalizationStateError):
            normalize_structured_quote(
                request_id,
                handoff_id,
                amount_minor=1000,
                currency="USD",
                scope_summary="Should not persist",
                actor="operator:ci",
            )


if __name__ == "__main__":
    unittest.main()
