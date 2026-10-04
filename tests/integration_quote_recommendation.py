import unittest
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from db import get_connection, get_request, get_request_events, save_request
from provider_directory import (
    add_provider_coverage_area,
    add_provider_service_capability,
    create_provider,
    set_provider_availability,
    set_provider_compliance,
)
from provider_selection import select_providers_for_request
from quote_normalization import normalize_structured_quote
from quote_recommendation import (
    QuoteRecommendationConflictError,
    get_quote_recommendation,
    recommend_quote_for_request,
)
from quote_award import (
    QuoteAwardConflictError,
    QuoteAwardEligibilityError,
    award_recommended_quote,
    get_quote_award,
)
from rfq_delivery import authorize_rfq_delivery, confirm_rfq_delivery
from rfq_handoff import prepare_rfq_handoff
from rfq_response import ingest_rfq_response
from delivery_handoff import (
    activate_delivery_handoff,
    get_delivery_handoff,
)
from delivery_notification import (
    get_prepared_delivery_notifications,
    prepare_delivery_notifications,
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


class QuoteRecommendationIntegrationTests(unittest.TestCase):
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

    def create_provider(self, name):
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

    def test_human_recommendation_is_immutable_and_not_an_award(self):
        request_id = save_request(
            "website",
            "CI Customer",
            "Need plumbing work",
            ready_analysis(),
        )
        self.request_ids.append(request_id)

        first = self.create_provider("CI Recommend A")
        second = self.create_provider("CI Recommend B")

        select_providers_for_request(
            request_id,
            "plumbing",
            "bn:brunei-muara",
            [first, second],
            actor="operator:ci",
        )
        rfq = prepare_rfq_handoff(request_id, actor="operator:ci")
        handoffs = {
            UUID(item["provider_id"]): UUID(item["handoff_id"])
            for item in rfq["provider_handoffs"]
        }

        quote_ids = {}
        comparison_as_of = None

        for provider_id, amount in (
            (first, 120000),
            (second, 100000),
        ):
            handoff_id = handoffs[provider_id]
            authorize_rfq_delivery(
                request_id,
                handoff_id,
                actor="operator:ci",
            )
            delivered = confirm_rfq_delivery(
                request_id,
                handoff_id,
                datetime.now(timezone.utc) + timedelta(hours=24),
                actor="operator:ci",
            )
            responded_at = delivered["delivered_at"] + timedelta(seconds=1)
            comparison_as_of = responded_at
            ingest_rfq_response(
                request_id,
                handoff_id,
                "quote",
                responded_at,
                actor="operator:ci",
            )
            normalized = normalize_structured_quote(
                request_id,
                handoff_id,
                amount_minor=amount,
                currency="AUD",
                scope_summary="Supply and replace leaking kitchen tap.",
                exclusions=["Wall repairs"],
                terms=["Payment on completion"],
                available_from=date(2026, 10, 10),
                estimated_duration_days=1,
                validity_expires_at=responded_at + timedelta(days=14),
                actor="operator:ci",
            )
            quote_ids[provider_id] = UUID(
                normalized["normalized_quote_id"]
            )

        chosen = quote_ids[second]
        first_result = recommend_quote_for_request(
            request_id,
            chosen,
            rationale="Human review preferred this scope and price.",
            actor="operator:ci",
        )
        retry = recommend_quote_for_request(
            request_id,
            chosen,
            rationale="Human review preferred this scope and price.",
            actor="operator:ci",
        )

        self.assertEqual(
            retry["recommendation_id"],
            first_result["recommendation_id"],
        )
        self.assertEqual(
            first_result["normalized_quote_id"],
            str(chosen),
        )
        self.assertEqual(
            first_result["recommendation_authority"],
            "human",
        )
        self.assertFalse(first_result["award_created"])
        self.assertFalse(first_result["provider_contacted"])

        with self.assertRaises(QuoteRecommendationConflictError):
            recommend_quote_for_request(
                request_id,
                quote_ids[first],
                rationale="Changed mind",
                actor="operator:ci",
            )

        persisted = get_quote_recommendation(request_id)
        self.assertEqual(
            persisted["recommendation_id"],
            first_result["recommendation_id"],
        )

        events = get_request_events(request_id)
        recommendation_events = [
            event
            for event in events
            if event["event_type"] == "quote_recommendation_recorded"
        ]
        self.assertEqual(len(recommendation_events), 1)
        self.assertFalse(
            recommendation_events[0]["details"]["award_created"]
        )
        self.assertFalse(
            recommendation_events[0]["details"]["provider_contacted"]
        )

        set_provider_compliance(second, "non_compliant")
        with self.assertRaises(QuoteAwardEligibilityError):
            award_recommended_quote(
                request_id,
                UUID(first_result["recommendation_id"]),
                reason="Human confirmed award after reviewing comparison.",
                actor="operator:ci",
            )
        set_provider_compliance(second, "compliant")

        award = award_recommended_quote(
            request_id,
            UUID(first_result["recommendation_id"]),
            reason="Human confirmed award after reviewing comparison.",
            actor="operator:ci",
        )
        award_retry = award_recommended_quote(
            request_id,
            UUID(first_result["recommendation_id"]),
            reason="Human confirmed award after reviewing comparison.",
            actor="operator:ci",
        )

        self.assertEqual(award_retry["award_id"], award["award_id"])
        self.assertEqual(award["normalized_quote_id"], str(chosen))
        self.assertEqual(award["award_authority"], "human")
        self.assertFalse(award["provider_contacted"])
        self.assertFalse(award["dispatch_created"])
        self.assertFalse(award["request_status_changed"])

        with self.assertRaises(QuoteAwardConflictError):
            award_recommended_quote(
                request_id,
                UUID(first_result["recommendation_id"]),
                reason="Different award reason",
                actor="operator:ci",
            )

        persisted_award = get_quote_award(request_id)
        self.assertEqual(persisted_award["award_id"], award["award_id"])

        award_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"] == "quote_award_recorded"
        ]
        self.assertEqual(len(award_events), 1)
        self.assertFalse(award_events[0]["details"]["provider_contacted"])
        self.assertFalse(award_events[0]["details"]["dispatch_created"])
        self.assertFalse(
            award_events[0]["details"]["request_status_changed"]
        )

        delivery = activate_delivery_handoff(
            request_id,
            UUID(award["award_id"]),
            actor="operator:ci",
        )
        delivery_retry = activate_delivery_handoff(
            request_id,
            UUID(award["award_id"]),
            actor="operator:ci",
        )

        self.assertEqual(
            delivery_retry["delivery_handoff_id"],
            delivery["delivery_handoff_id"],
        )
        self.assertEqual(delivery["request_status"], "actioned")
        self.assertEqual(delivery["provider_id"], str(second))
        self.assertEqual(delivery["amount_minor"], 100000)
        self.assertEqual(delivery["currency"], "AUD")
        self.assertFalse(delivery["provider_contacted"])
        self.assertFalse(delivery["dispatch_created"])
        self.assertFalse(delivery["appointment_created"])

        persisted_delivery = get_delivery_handoff(request_id)
        self.assertEqual(
            persisted_delivery["delivery_handoff_id"],
            delivery["delivery_handoff_id"],
        )
        self.assertEqual(get_request(request_id)["status"], "actioned")
        self.assertIsNotNone(get_request(request_id)["actioned_at"])

        delivery_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"] == "delivery_handoff_activated"
        ]
        self.assertEqual(len(delivery_events), 1)
        self.assertEqual(
            delivery_events[0]["details"]["new_status"],
            "actioned",
        )
        self.assertFalse(
            delivery_events[0]["details"]["provider_contacted"]
        )
        self.assertFalse(
            delivery_events[0]["details"]["dispatch_created"]
        )
        self.assertFalse(
            delivery_events[0]["details"]["appointment_created"]
        )

        prepared = prepare_delivery_notifications(
            request_id,
            actor="operator:ci",
        )
        prepared_retry = prepare_delivery_notifications(
            request_id,
            actor="operator:ci",
        )

        self.assertEqual(len(prepared["notifications"]), 2)
        self.assertEqual(
            {
                item["audience_type"]
                for item in prepared["notifications"]
            },
            {"customer", "provider"},
        )
        self.assertEqual(
            [item["notification_id"] for item in prepared_retry["notifications"]],
            [item["notification_id"] for item in prepared["notifications"]],
        )
        self.assertFalse(prepared["destinations_resolved"])
        self.assertFalse(prepared["sent"])
        for item in prepared["notifications"]:
            self.assertIsNone(item["destination_channel"])
            self.assertIsNone(item["destination_address"])
            self.assertEqual(item["status"], "prepared")
            self.assertFalse(item["sent"])
            self.assertFalse(item["external_action_performed"])

        persisted_notifications = get_prepared_delivery_notifications(
            request_id
        )
        self.assertEqual(len(persisted_notifications), 2)

        notification_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"] == "delivery_notifications_prepared"
        ]
        self.assertEqual(len(notification_events), 1)
        self.assertFalse(
            notification_events[0]["details"]["destinations_resolved"]
        )
        self.assertFalse(notification_events[0]["details"]["sent"])
        self.assertFalse(
            notification_events[0]["details"]["external_action_performed"]
        )


if __name__ == "__main__":
    unittest.main()
