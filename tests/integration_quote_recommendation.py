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
from delivery_appointment import (
    confirm_delivery_appointment,
    get_delivery_appointment,
    propose_delivery_appointment,
)
from delivery_status import (
    get_delivery_status,
    initialize_delivery_status,
    start_delivery,
)
from delivery_exception import (
    get_delivery_exceptions,
    record_delivery_exception,
)
from human_intervention import (
    acknowledge_human_intervention,
    create_human_intervention,
    get_human_interventions,
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

        proposed_start = datetime.now(timezone.utc) + timedelta(days=2)
        proposed_end = proposed_start + timedelta(hours=2)
        appointment = propose_delivery_appointment(
            request_id,
            proposed_start,
            proposed_end,
            reason="Human coordinated a proposed service window.",
            actor="operator:ci",
        )
        appointment_retry = propose_delivery_appointment(
            request_id,
            proposed_start,
            proposed_end,
            reason="Human coordinated a proposed service window.",
            actor="operator:ci",
        )

        self.assertEqual(
            appointment_retry["appointment_id"],
            appointment["appointment_id"],
        )
        self.assertEqual(appointment["status"], "proposed")
        self.assertEqual(
            appointment["proposed_start_at"],
            proposed_start,
        )
        self.assertEqual(
            appointment["proposed_end_at"],
            proposed_end,
        )
        self.assertFalse(
            appointment["external_calendar_booking_created"]
        )
        self.assertFalse(appointment["notification_sent"])

        confirmed = confirm_delivery_appointment(
            request_id,
            UUID(appointment["appointment_id"]),
            reason="Human confirmed both parties agreed to the window.",
            actor="operator:ci",
        )
        confirmed_retry = confirm_delivery_appointment(
            request_id,
            UUID(appointment["appointment_id"]),
            reason="Human confirmed both parties agreed to the window.",
            actor="operator:ci",
        )

        self.assertEqual(
            confirmed_retry["appointment_id"],
            confirmed["appointment_id"],
        )
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertIsNotNone(confirmed["confirmed_at"])
        self.assertFalse(
            confirmed["external_calendar_booking_created"]
        )
        self.assertFalse(confirmed["notification_sent"])

        persisted_appointment = get_delivery_appointment(request_id)
        self.assertEqual(
            persisted_appointment["appointment_id"],
            appointment["appointment_id"],
        )
        self.assertEqual(
            persisted_appointment["status"],
            "confirmed",
        )

        appointment_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"].startswith("delivery_appointment_")
        ]
        self.assertEqual(
            [event["event_type"] for event in appointment_events],
            [
                "delivery_appointment_proposed",
                "delivery_appointment_confirmed",
            ],
        )
        for event in appointment_events:
            self.assertFalse(
                event["details"]["external_calendar_booking_created"]
            )
            self.assertFalse(event["details"]["notification_sent"])

        delivery_status = initialize_delivery_status(
            request_id,
            UUID(appointment["appointment_id"]),
            reason="Human scheduled delivery after appointment confirmation.",
            actor="operator:ci",
        )
        delivery_status_retry = initialize_delivery_status(
            request_id,
            UUID(appointment["appointment_id"]),
            reason="Human scheduled delivery after appointment confirmation.",
            actor="operator:ci",
        )

        self.assertEqual(
            delivery_status_retry["delivery_status_id"],
            delivery_status["delivery_status_id"],
        )
        self.assertEqual(delivery_status["status"], "scheduled")
        self.assertFalse(delivery_status["completion_recorded"])
        self.assertFalse(delivery_status["exception_recorded"])
        self.assertFalse(delivery_status["notification_sent"])

        started = start_delivery(
            request_id,
            UUID(delivery_status["delivery_status_id"]),
            reason="Human confirmed service work has started.",
            actor="operator:ci",
        )
        started_retry = start_delivery(
            request_id,
            UUID(delivery_status["delivery_status_id"]),
            reason="Human confirmed service work has started.",
            actor="operator:ci",
        )

        self.assertEqual(
            started_retry["delivery_status_id"],
            started["delivery_status_id"],
        )
        self.assertEqual(started["status"], "in_progress")
        self.assertIsNotNone(started["started_at"])
        self.assertFalse(started["completion_recorded"])
        self.assertFalse(started["exception_recorded"])
        self.assertFalse(started["notification_sent"])

        persisted_status = get_delivery_status(request_id)
        self.assertEqual(
            persisted_status["delivery_status_id"],
            delivery_status["delivery_status_id"],
        )
        self.assertEqual(persisted_status["status"], "in_progress")

        status_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"].startswith("delivery_status_")
        ]
        self.assertEqual(
            [event["event_type"] for event in status_events],
            [
                "delivery_status_scheduled",
                "delivery_status_in_progress",
            ],
        )
        for event in status_events:
            self.assertFalse(event["details"]["completion_recorded"])
            self.assertFalse(event["details"]["exception_recorded"])
            self.assertFalse(event["details"]["notification_sent"])

        delay_id = uuid4()
        occurred_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        expected_resolution_at = occurred_at + timedelta(hours=1)
        delay = record_delivery_exception(
            request_id,
            UUID(delivery_status["delivery_status_id"]),
            delay_id,
            "delay",
            occurred_at,
            summary="Provider reported a one-hour delay.",
            expected_resolution_at=expected_resolution_at,
            actor="operator:ci",
        )
        delay_retry = record_delivery_exception(
            request_id,
            UUID(delivery_status["delivery_status_id"]),
            delay_id,
            "delay",
            occurred_at,
            summary="Provider reported a one-hour delay.",
            expected_resolution_at=expected_resolution_at,
            actor="operator:ci",
        )

        self.assertEqual(delay_retry["exception_id"], delay["exception_id"])
        self.assertEqual(delay["exception_kind"], "delay")
        self.assertFalse(delay["resolved"])
        self.assertFalse(delay["human_intervention_created"])
        self.assertFalse(delay["notification_sent"])

        issue_id = uuid4()
        issue = record_delivery_exception(
            request_id,
            UUID(delivery_status["delivery_status_id"]),
            issue_id,
            "service_issue",
            occurred_at + timedelta(minutes=1),
            summary="Unexpected access issue encountered during service.",
            actor="operator:ci",
        )
        self.assertEqual(issue["exception_kind"], "service_issue")

        persisted_exceptions = get_delivery_exceptions(request_id)
        self.assertEqual(
            [item["exception_id"] for item in persisted_exceptions],
            [str(delay_id), str(issue_id)],
        )

        exception_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"] == "delivery_exception_recorded"
        ]
        self.assertEqual(len(exception_events), 2)
        self.assertEqual(
            [event["details"]["exception_kind"] for event in exception_events],
            ["delay", "service_issue"],
        )
        for event in exception_events:
            self.assertFalse(event["details"]["resolved"])
            self.assertFalse(
                event["details"]["human_intervention_created"]
            )
            self.assertFalse(event["details"]["notification_sent"])

        intervention = create_human_intervention(
            request_id,
            issue_id,
            priority="high",
            reason="Operator intervention required for service issue.",
            actor="operator:ci",
        )
        intervention_retry = create_human_intervention(
            request_id,
            issue_id,
            priority="high",
            reason="Operator intervention required for service issue.",
            actor="operator:ci",
        )

        self.assertEqual(
            intervention_retry["intervention_id"],
            intervention["intervention_id"],
        )
        self.assertEqual(intervention["status"], "open")
        self.assertEqual(intervention["priority"], "high")
        self.assertFalse(intervention["exception_resolved"])
        self.assertFalse(intervention["delivery_status_changed"])
        self.assertFalse(intervention["notification_sent"])

        exceptions_after_queue = get_delivery_exceptions(request_id)
        issue_after_queue = next(
            item
            for item in exceptions_after_queue
            if item["exception_id"] == str(issue_id)
        )
        self.assertTrue(issue_after_queue["human_intervention_created"])

        acknowledged = acknowledge_human_intervention(
            request_id,
            UUID(intervention["intervention_id"]),
            reason="Operator has taken ownership of the intervention.",
            actor="operator:ci",
        )
        acknowledged_retry = acknowledge_human_intervention(
            request_id,
            UUID(intervention["intervention_id"]),
            reason="Operator has taken ownership of the intervention.",
            actor="operator:ci",
        )

        self.assertEqual(
            acknowledged_retry["intervention_id"],
            acknowledged["intervention_id"],
        )
        self.assertEqual(acknowledged["status"], "acknowledged")
        self.assertIsNotNone(acknowledged["acknowledged_at"])
        self.assertFalse(acknowledged["exception_resolved"])
        self.assertFalse(acknowledged["delivery_status_changed"])
        self.assertFalse(acknowledged["notification_sent"])

        persisted_interventions = get_human_interventions(request_id)
        self.assertEqual(len(persisted_interventions), 1)
        self.assertEqual(
            persisted_interventions[0]["intervention_id"],
            intervention["intervention_id"],
        )
        self.assertEqual(
            persisted_interventions[0]["status"],
            "acknowledged",
        )

        intervention_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"].startswith("human_intervention_")
        ]
        self.assertEqual(
            [event["event_type"] for event in intervention_events],
            [
                "human_intervention_created",
                "human_intervention_acknowledged",
            ],
        )
        for event in intervention_events:
            self.assertFalse(event["details"]["exception_resolved"])
            self.assertFalse(event["details"]["delivery_status_changed"])
            self.assertFalse(event["details"]["notification_sent"])


if __name__ == "__main__":
    unittest.main()
