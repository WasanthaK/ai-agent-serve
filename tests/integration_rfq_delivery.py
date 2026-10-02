import unittest
from datetime import datetime, timedelta, timezone
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
from rfq_delivery import (
    RFQDeliveryConflictError,
    RFQDeliveryEligibilityError,
    RFQDeliveryStateError,
    authorize_rfq_delivery,
    confirm_rfq_delivery,
)
from rfq_handoff import prepare_rfq_handoff
from rfq_response import RFQResponseConflictError, ingest_rfq_response


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


class RFQDeliveryIntegrationTests(unittest.TestCase):
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

    def create_request_and_handoff(self):
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
            "CI Delivery Provider",
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
        rfq = prepare_rfq_handoff(
            request_id,
            actor="operator:ci",
        )
        handoff_id = UUID(rfq["provider_handoffs"][0]["handoff_id"])
        return request_id, provider_id, handoff_id

    def test_authorize_then_confirm_creates_one_response_opportunity(self):
        request_id, provider_id, handoff_id = self.create_request_and_handoff()

        authorized = authorize_rfq_delivery(
            request_id,
            handoff_id,
            actor="operator:ci",
        )
        self.assertEqual(authorized["status"], "authorized")
        self.assertIsNotNone(authorized["authorized_at"])
        self.assertFalse(authorized["response_reliability_started"])

        deadline = datetime.now(timezone.utc) + timedelta(hours=24)
        delivered = confirm_rfq_delivery(
            request_id,
            handoff_id,
            deadline,
            actor="operator:ci",
        )
        self.assertEqual(delivered["status"], "delivered")
        self.assertTrue(delivered["response_reliability_started"])
        self.assertIsNotNone(delivered["delivered_at"])
        self.assertEqual(delivered["response_deadline_at"], deadline)

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT provider_id, opportunity_id, offered_at,
                           response_deadline_at
                    FROM provider_response_opportunities
                    WHERE provider_id = %s
                      AND opportunity_id = %s
                    """,
                    (provider_id, handoff_id),
                )
                opportunity = cur.fetchone()
                self.assertIsNotNone(opportunity)
                self.assertEqual(opportunity[0], provider_id)
                self.assertEqual(opportunity[1], handoff_id)
                self.assertEqual(opportunity[3], deadline)

        retry = confirm_rfq_delivery(
            request_id,
            handoff_id,
            deadline,
            actor="operator:ci",
        )
        self.assertEqual(retry["delivered_at"], delivered["delivered_at"])

        with self.assertRaises(RFQDeliveryConflictError):
            confirm_rfq_delivery(
                request_id,
                handoff_id,
                deadline + timedelta(hours=1),
                actor="operator:ci",
            )

        events = get_request_events(request_id)
        self.assertEqual(
            len([
                event for event in events
                if event["event_type"] == "rfq_delivery_authorized"
            ]),
            1,
        )
        self.assertEqual(
            len([
                event for event in events
                if event["event_type"] == "rfq_delivery_confirmed"
            ]),
            1,
        )

    def test_authorization_fails_if_provider_is_no_longer_eligible(self):
        request_id, provider_id, handoff_id = self.create_request_and_handoff()
        set_provider_availability(provider_id, "unavailable")

        with self.assertRaises(RFQDeliveryEligibilityError):
            authorize_rfq_delivery(
                request_id,
                handoff_id,
                actor="operator:ci",
            )

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status
                    FROM rfq_provider_handoffs
                    WHERE id = %s
                    """,
                    (handoff_id,),
                )
                self.assertEqual(cur.fetchone()[0], "prepared")

    def test_confirmation_requires_prior_authorization(self):
        request_id, _provider_id, handoff_id = self.create_request_and_handoff()
        deadline = datetime.now(timezone.utc) + timedelta(hours=24)

        with self.assertRaises(RFQDeliveryStateError):
            confirm_rfq_delivery(
                request_id,
                handoff_id,
                deadline,
                actor="operator:ci",
            )

    def test_confirmation_rechecks_eligibility(self):
        request_id, provider_id, handoff_id = self.create_request_and_handoff()
        authorize_rfq_delivery(
            request_id,
            handoff_id,
            actor="operator:ci",
        )
        set_provider_compliance(provider_id, "non_compliant")

        with self.assertRaises(RFQDeliveryEligibilityError):
            confirm_rfq_delivery(
                request_id,
                handoff_id,
                datetime.now(timezone.utc) + timedelta(hours=24),
                actor="operator:ci",
            )


    def test_delivered_handoff_accepts_governed_provider_response(self):
        request_id, provider_id, handoff_id = self.create_request_and_handoff()
        authorize_rfq_delivery(request_id, handoff_id, actor="operator:ci")
        confirm_rfq_delivery(
            request_id,
            handoff_id,
            datetime.now(timezone.utc) + timedelta(hours=24),
            actor="operator:ci",
        )
        responded_at = datetime.now(timezone.utc)

        first = ingest_rfq_response(
            request_id,
            handoff_id,
            "quote",
            responded_at,
            actor="operator:ci",
        )
        retry = ingest_rfq_response(
            request_id,
            handoff_id,
            "quote",
            responded_at,
            actor="operator:ci",
        )

        self.assertEqual(first["response_id"], retry["response_id"])
        self.assertEqual(first["provider_id"], str(provider_id))

        with self.assertRaises(RFQResponseConflictError):
            ingest_rfq_response(
                request_id,
                handoff_id,
                "decline",
                responded_at,
                actor="operator:ci",
            )

        events = get_request_events(request_id)
        self.assertEqual(
            len([
                event for event in events
                if event["event_type"] == "rfq_provider_response_recorded"
            ]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
