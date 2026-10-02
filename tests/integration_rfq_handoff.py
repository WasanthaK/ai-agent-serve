import unittest
from uuid import UUID, uuid4

from db import (
    get_connection,
    get_request_events,
    save_request,
    update_request_status,
)
from provider_directory import (
    add_provider_coverage_area,
    add_provider_service_capability,
    create_provider,
    set_provider_availability,
    set_provider_compliance,
)
from provider_selection import select_providers_for_request
from rfq_handoff import (
    RFQHandoffNotFoundError,
    RFQHandoffStateError,
    get_rfq_for_request,
    prepare_rfq_handoff,
)


def ready_analysis():
    return {
        "intent": "Request a quote",
        "category": "plumbing",
        "summary": "Replace a leaking kitchen tap",
        "urgency": "normal",
        "next_action": "Route to providers",
        "needs_human_review": False,
        "missing_information": [],
        "follow_up_questions": [],
    }


class RFQHandoffIntegrationTests(unittest.TestCase):
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

    def create_request(self):
        request_id = save_request(
            "website",
            "Private Customer Name",
            "Private raw customer message with unnecessary details",
            ready_analysis(),
        )
        self.request_ids.append(request_id)
        return request_id

    def create_eligible_provider(self, name):
        provider_id = uuid4()
        self.provider_ids.append(provider_id)
        create_provider(
            name,
            approval_status="approved",
            provider_id=provider_id,
        )
        add_provider_service_capability(provider_id, "plumbing")
        add_provider_coverage_area(provider_id, "bn:brunei-muara")
        set_provider_availability(provider_id, "available")
        set_provider_compliance(provider_id, "compliant")
        return provider_id

    def select(self, request_id, provider_ids):
        return select_providers_for_request(
            request_id,
            "plumbing",
            "bn:brunei-muara",
            provider_ids,
            actor="operator:ci",
            reason="Human-approved RFQ recipient set",
        )

    def test_prepares_provider_specific_handoffs_without_delivery_or_reliability_start(self):
        request_id = self.create_request()
        first = self.create_eligible_provider("CI RFQ Provider A")
        second = self.create_eligible_provider("CI RFQ Provider B")
        selection = self.select(request_id, [second, first])

        rfq = prepare_rfq_handoff(
            request_id,
            actor="operator:ci",
        )

        self.assertEqual(rfq["request_id"], str(request_id))
        self.assertEqual(rfq["selection_id"], selection["selection_id"])
        self.assertEqual(rfq["service_slug"], "plumbing")
        self.assertEqual(rfq["area_key"], "bn:brunei-muara")
        self.assertEqual(rfq["scope_summary"], "Replace a leaking kitchen tap")
        self.assertEqual(rfq["urgency"], "normal")
        self.assertEqual(rfq["status"], "prepared")
        self.assertEqual(rfq["prepared_by"], "operator:ci")
        self.assertEqual(rfq["provider_count"], 2)
        self.assertFalse(rfq["delivery_started"])
        self.assertEqual(
            sorted(item["provider_id"] for item in rfq["provider_handoffs"]),
            sorted([str(first), str(second)]),
        )
        self.assertTrue(all(
            item["status"] == "prepared"
            for item in rfq["provider_handoffs"]
        ))

        # RFQ snapshots deliberately exclude raw customer message/name.
        self.assertNotIn("customer_name", rfq)
        self.assertNotIn("message", rfq)
        self.assertNotIn("Private Customer Name", str(rfq))
        self.assertNotIn("Private raw customer message", str(rfq))

        persisted = get_rfq_for_request(request_id)
        self.assertEqual(persisted["rfq_id"], rfq["rfq_id"])

        events = get_request_events(request_id)
        rfq_events = [
            event for event in events
            if event["event_type"] == "rfq_handoff_prepared"
        ]
        self.assertEqual(len(rfq_events), 1)
        self.assertFalse(rfq_events[0]["details"]["delivery_started"])
        self.assertFalse(
            rfq_events[0]["details"]["response_reliability_started"]
        )
        self.assertEqual(rfq_events[0]["details"]["provider_count"], 2)

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM provider_response_opportunities
                    WHERE opportunity_id = ANY(%s)
                    """,
                    ([UUID(item["handoff_id"]) for item in rfq["provider_handoffs"]],),
                )
                self.assertEqual(cur.fetchone()[0], 0)

    def test_exact_retry_returns_original_rfq_even_after_request_rejection(self):
        request_id = self.create_request()
        provider_id = self.create_eligible_provider("CI RFQ Retry Provider")
        self.select(request_id, [provider_id])

        first = prepare_rfq_handoff(
            request_id,
            actor="operator:ci",
        )

        update_request_status(
            request_id,
            new_status="rejected",
            actor="operator:ci",
            event_type="request_rejected",
            details={"reason": "Customer cancelled"},
        )

        retry = prepare_rfq_handoff(
            request_id,
            actor="operator:other",
        )

        self.assertEqual(retry["rfq_id"], first["rfq_id"])
        self.assertEqual(
            [item["handoff_id"] for item in retry["provider_handoffs"]],
            [item["handoff_id"] for item in first["provider_handoffs"]],
        )

        events = get_request_events(request_id)
        self.assertEqual(
            len([
                event for event in events
                if event["event_type"] == "rfq_handoff_prepared"
            ]),
            1,
        )

    def test_selection_is_required_before_rfq_preparation(self):
        request_id = self.create_request()

        with self.assertRaises(RFQHandoffNotFoundError):
            prepare_rfq_handoff(
                request_id,
                actor="operator:ci",
            )

        self.assertIsNone(get_rfq_for_request(request_id))

    def test_rejected_request_cannot_prepare_first_rfq(self):
        request_id = self.create_request()
        provider_id = self.create_eligible_provider("CI RFQ State Provider")
        self.select(request_id, [provider_id])

        update_request_status(
            request_id,
            new_status="rejected",
            actor="operator:ci",
            event_type="request_rejected",
        )

        with self.assertRaises(RFQHandoffStateError):
            prepare_rfq_handoff(
                request_id,
                actor="operator:ci",
            )

        self.assertIsNone(get_rfq_for_request(request_id))


if __name__ == "__main__":
    unittest.main()
