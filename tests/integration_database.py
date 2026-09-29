import unittest
from uuid import uuid4

from db import get_connection, get_request, get_request_events, save_request
from inbound import InboundAttachment, InboundSender, NormalizedInboundMessage
from inbound_persistence import (
    InboundMessageConflictError,
    InboundMessageLinkConflictError,
    get_inbound_message,
    link_inbound_message_to_request,
    save_inbound_message,
)
from provider_directory import (
    add_provider_coverage_area,
    add_provider_service_capability,
    create_provider,
    get_provider,
    list_approved_providers,
    list_approved_providers_for_service,
    list_approved_providers_for_service_and_area,
    list_provider_coverage_areas,
    list_provider_service_capabilities,
)


ANALYSIS = {
    "intent": "Request a quote",
    "category": "Plumbing",
    "summary": "Synthetic CI request",
    "urgency": "normal",
    "next_action": "Collect missing information",
    "needs_human_review": False,
    "missing_information": ["service_location"],
    "follow_up_questions": ["Where is the service required?"],
}


class DatabaseIntegrationTests(unittest.TestCase):
    def test_request_and_event_round_trip_on_fresh_schema(self):
        request_id = save_request(
            source="website",
            customer_name="CI Integration",
            message="Synthetic integration test request",
            result=dict(ANALYSIS),
            skill_versions={"request_intake": "1.0.0"},
        )

        try:
            saved = get_request(request_id)
            self.assertIsNotNone(saved)
            self.assertEqual(saved["source"], "website")
            self.assertEqual(saved["status"], "needs_information")
            self.assertEqual(saved["missing_information"], ["service_location"])

            events = get_request_events(request_id)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "request_created")
            self.assertEqual(
                events[0]["details"]["skill_versions"],
                {"request_intake": "1.0.0"},
            )
        finally:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM agent_requests WHERE id = %s",
                        (request_id,),
                    )

    def test_normalized_inbound_message_round_trip_and_retry_safety(self):
        external_message_id = f"ci-email-{uuid4()}"
        normalized = NormalizedInboundMessage(
            channel="email",
            text="Subject: Leaking tap\n\nPlease quote this repair.",
            sender=InboundSender(
                address="customer@example.com",
                display_name="CI Customer",
            ),
            external_message_id=external_message_id,
            external_conversation_id="thread-ci-123",
            attachments=[
                InboundAttachment(
                    reference="attachment-ci-1",
                    media_type="image/jpeg",
                    filename="tap.jpg",
                    size_bytes=2048,
                )
            ],
        )

        first = save_inbound_message(normalized)
        message_id = first["message"]["id"]

        try:
            self.assertEqual(first["action"], "created")
            stored = get_inbound_message(message_id)
            self.assertEqual(stored["channel"], "email")
            self.assertEqual(stored["sender"]["address"], "customer@example.com")
            self.assertEqual(
                stored["external_conversation_id"],
                "thread-ci-123",
            )
            self.assertEqual(stored["attachments"][0]["filename"], "tap.jpg")

            duplicate = save_inbound_message(normalized)
            self.assertEqual(duplicate["action"], "duplicate")
            self.assertEqual(duplicate["message"]["id"], message_id)

            conflicting = normalized.model_copy(
                update={"text": "Different content under the same provider ID"}
            )
            with self.assertRaises(InboundMessageConflictError):
                save_inbound_message(conflicting)
        finally:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM inbound_messages WHERE id = %s",
                        (message_id,),
                    )

    def test_inbound_message_links_to_one_internal_request_idempotently(self):
        normalized = NormalizedInboundMessage(
            channel="email",
            text="Please quote a leaking tap.",
            sender=InboundSender(address="customer@example.com"),
            external_message_id=f"ci-email-link-{uuid4()}",
        )
        inbound = save_inbound_message(normalized)
        inbound_id = inbound["message"]["id"]

        request_id = save_request(
            source="email",
            customer_name="CI Customer",
            message=normalized.text,
            result=dict(ANALYSIS),
        )

        try:
            linked = link_inbound_message_to_request(inbound_id, request_id)
            self.assertEqual(linked["linked_request_id"], request_id)

            linked_again = link_inbound_message_to_request(inbound_id, request_id)
            self.assertEqual(linked_again["linked_request_id"], request_id)

            with self.assertRaises(InboundMessageLinkConflictError):
                link_inbound_message_to_request(inbound_id, uuid4())
        finally:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM inbound_messages WHERE id = %s",
                        (inbound_id,),
                    )
                    cur.execute(
                        "DELETE FROM agent_requests WHERE id = %s",
                        (request_id,),
                    )

    def test_provider_directory_round_trip_and_approved_filter(self):
        approved_id = uuid4()
        pending_id = uuid4()

        approved = create_provider(
            "CI Approved Plumbing",
            approval_status="approved",
            provider_id=approved_id,
        )
        pending = create_provider(
            "CI Pending Plumbing",
            approval_status="pending",
            provider_id=pending_id,
        )

        try:
            self.assertEqual(approved["id"], approved_id)
            self.assertEqual(approved["approval_status"], "approved")
            self.assertEqual(pending["approval_status"], "pending")

            stored = get_provider(approved_id)
            self.assertEqual(stored["display_name"], "CI Approved Plumbing")

            approved_directory = list_approved_providers()
            approved_ids = {provider["id"] for provider in approved_directory}
            self.assertIn(approved_id, approved_ids)
            self.assertNotIn(pending_id, approved_ids)
        finally:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM providers WHERE id IN (%s, %s)",
                        (approved_id, pending_id),
                    )

    def test_provider_service_capability_uses_canonical_slug_and_approval_filter(self):
        approved_id = uuid4()
        pending_id = uuid4()
        unrelated_id = uuid4()

        create_provider(
            "CI Approved Plumber",
            approval_status="approved",
            provider_id=approved_id,
        )
        create_provider(
            "CI Pending Plumber",
            approval_status="pending",
            provider_id=pending_id,
        )
        create_provider(
            "CI Approved Electrician",
            approval_status="approved",
            provider_id=unrelated_id,
        )

        try:
            first = add_provider_service_capability(approved_id, "plumbing")
            duplicate = add_provider_service_capability(approved_id, "plumbing")
            add_provider_service_capability(pending_id, "plumbing")
            add_provider_service_capability(unrelated_id, "electrical")

            self.assertEqual(first["provider_id"], approved_id)
            self.assertEqual(first["service_slug"], "plumbing")
            self.assertEqual(duplicate["provider_id"], approved_id)

            capabilities = list_provider_service_capabilities(approved_id)
            self.assertEqual(
                [capability["service_slug"] for capability in capabilities],
                ["plumbing"],
            )

            matching = list_approved_providers_for_service("plumbing")
            matching_ids = {provider["id"] for provider in matching}
            self.assertIn(approved_id, matching_ids)
            self.assertNotIn(pending_id, matching_ids)
            self.assertNotIn(unrelated_id, matching_ids)
        finally:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM providers WHERE id IN (%s, %s, %s)",
                        (approved_id, pending_id, unrelated_id),
                    )

    def test_provider_coverage_area_exact_service_area_eligibility(self):
        approved_local_id = uuid4()
        approved_other_area_id = uuid4()
        pending_local_id = uuid4()

        for provider_id, name, status in (
            (approved_local_id, "CI Local Approved Plumber", "approved"),
            (approved_other_area_id, "CI Other Area Plumber", "approved"),
            (pending_local_id, "CI Local Pending Plumber", "pending"),
        ):
            create_provider(
                name,
                approval_status=status,
                provider_id=provider_id,
            )
            add_provider_service_capability(provider_id, "plumbing")

        try:
            first = add_provider_coverage_area(
                approved_local_id,
                "bn:brunei-muara",
            )
            duplicate = add_provider_coverage_area(
                approved_local_id,
                "bn:brunei-muara",
            )
            add_provider_coverage_area(
                approved_other_area_id,
                "bn:tutong",
            )
            add_provider_coverage_area(
                pending_local_id,
                "bn:brunei-muara",
            )

            self.assertEqual(first["provider_id"], approved_local_id)
            self.assertEqual(first["area_key"], "bn:brunei-muara")
            self.assertEqual(duplicate["provider_id"], approved_local_id)

            areas = list_provider_coverage_areas(approved_local_id)
            self.assertEqual(
                [area["area_key"] for area in areas],
                ["bn:brunei-muara"],
            )

            matching = list_approved_providers_for_service_and_area(
                "plumbing",
                "bn:brunei-muara",
            )
            matching_ids = {provider["id"] for provider in matching}
            self.assertIn(approved_local_id, matching_ids)
            self.assertNotIn(approved_other_area_id, matching_ids)
            self.assertNotIn(pending_local_id, matching_ids)
        finally:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM providers WHERE id IN (%s, %s, %s)",
                        (
                            approved_local_id,
                            approved_other_area_id,
                            pending_local_id,
                        ),
                    )


if __name__ == "__main__":
    unittest.main()
