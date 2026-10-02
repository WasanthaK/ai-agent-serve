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
from rfq_delivery import authorize_rfq_delivery, confirm_rfq_delivery
from rfq_handoff import prepare_rfq_handoff
from rfq_response import (
    RFQResponseConflictError,
    RFQResponseStateError,
    ingest_rfq_response,
)


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


class RFQResponseIntegrationTests(unittest.TestCase):
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

    def create_handoff(self, delivered=True):
        request_id = save_request(
            "website", "CI Customer", "Need plumbing work", ready_analysis()
        )
        self.request_ids.append(request_id)
        provider_id = uuid4()
        self.provider_ids.append(provider_id)
        create_provider(
            "CI Response Provider",
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
        if delivered:
            authorize_rfq_delivery(request_id, handoff_id, actor="operator:ci")
            confirm_rfq_delivery(
                request_id,
                handoff_id,
                datetime.now(timezone.utc) + timedelta(hours=24),
                actor="operator:ci",
            )
        return request_id, provider_id, handoff_id

    def test_delivered_handoff_accepts_one_idempotent_response(self):
        request_id, provider_id, handoff_id = self.create_handoff()
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
        recorded = [
            event for event in events
            if event["event_type"] == "rfq_provider_response_recorded"
        ]
        self.assertEqual(len(recorded), 1)

    def test_response_requires_delivered_handoff(self):
        request_id, _provider_id, handoff_id = self.create_handoff(delivered=False)
        with self.assertRaises(RFQResponseStateError):
            ingest_rfq_response(
                request_id,
                handoff_id,
                "decline",
                datetime.now(timezone.utc),
                actor="operator:ci",
            )


if __name__ == "__main__":
    unittest.main()
