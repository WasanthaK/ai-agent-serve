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
    DeliveryStatusStateError,
    complete_delivery,
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
from delivery_timeline import get_delivery_timeline
from satisfaction_follow_up import (
    SatisfactionFollowUpConflictError,
    get_satisfaction_follow_up,
    prepare_satisfaction_follow_up,
    record_satisfaction_response,
)
from review_request import (
    get_review_request,
    prepare_review_request,
)
from closure_escalation import (
    create_closure_escalation,
    get_closure_escalations,
)
from outcome_measurement import get_outcome_measurement
from skill_evaluation import (
    SkillEvaluationConflictError,
    create_skill_evaluation,
    get_skill_evaluations,
)
from skill_improvement import (
    SkillImprovementConflictError,
    SkillImprovementStateError,
    create_skill_improvement_proposal,
    get_skill_improvement_proposals,
)
from skill_regression import (
    SkillRegressionConflictError,
    record_skill_regression_test,
    get_skill_regression_tests,
)
from skill_revision import (
    SkillRevisionConflictError,
    create_skill_improvement_revision,
    get_skill_improvement_revisions,
)
from training_workspace import (
    get_training_case,
    list_training_cases,
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
            skill_versions={
                "request_intake": "1.0.0",
                "request_clarification": "1.0.0",
            },
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

        with self.assertRaises(DeliveryStatusStateError):
            complete_delivery(
                request_id,
                UUID(delivery_status["delivery_status_id"]),
                reason="Human confirmed service work is complete.",
                actor="operator:ci",
            )

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

        completed = complete_delivery(
            request_id,
            UUID(delivery_status["delivery_status_id"]),
            reason="Human confirmed service work is complete.",
            actor="operator:ci",
        )
        completed_retry = complete_delivery(
            request_id,
            UUID(delivery_status["delivery_status_id"]),
            reason="Human confirmed service work is complete.",
            actor="operator:ci",
        )

        self.assertEqual(
            completed_retry["delivery_status_id"],
            completed["delivery_status_id"],
        )
        self.assertEqual(completed["status"], "completed")
        self.assertTrue(completed["completion_recorded"])
        self.assertTrue(completed["exception_recorded"])
        self.assertIsNotNone(completed["completed_at"])
        self.assertFalse(completed["notification_sent"])

        persisted_completed = get_delivery_status(request_id)
        self.assertEqual(persisted_completed["status"], "completed")
        self.assertTrue(persisted_completed["completion_recorded"])
        self.assertTrue(persisted_completed["exception_recorded"])
        self.assertEqual(get_request(request_id)["status"], "actioned")

        completion_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"] == "delivery_status_completed"
        ]
        self.assertEqual(len(completion_events), 1)
        self.assertTrue(
            completion_events[0]["details"]["exception_recorded"]
        )
        self.assertEqual(
            completion_events[0]["details"]["open_intervention_count"],
            0,
        )
        self.assertFalse(
            completion_events[0]["details"]["notification_sent"]
        )

        timeline = get_delivery_timeline(request_id)
        timeline_types = [
            item["event_type"]
            for item in timeline["timeline"]
        ]
        self.assertEqual(
            timeline["event_count"],
            len(timeline["timeline"]),
        )
        self.assertEqual(
            [item["sequence"] for item in timeline["timeline"]],
            list(range(1, timeline["event_count"] + 1)),
        )
        self.assertEqual(timeline["latest_stage"], "completion")
        self.assertTrue(timeline["delivery_completed"])
        self.assertTrue(timeline["has_exceptions"])
        self.assertTrue(timeline["has_interventions"])
        self.assertEqual(
            timeline_types,
            [
                "delivery_handoff_activated",
                "delivery_notifications_prepared",
                "delivery_appointment_proposed",
                "delivery_appointment_confirmed",
                "delivery_status_scheduled",
                "delivery_status_in_progress",
                "delivery_exception_recorded",
                "delivery_exception_recorded",
                "human_intervention_created",
                "human_intervention_acknowledged",
                "delivery_status_completed",
            ],
        )
        for item in timeline["timeline"]:
            self.assertIsNotNone(item["event_id"])
            self.assertIsNotNone(item["actor"])
            self.assertIsNotNone(item["created_at"])
            self.assertIn("details", item)

        follow_up = prepare_satisfaction_follow_up(
            request_id,
            actor="operator:ci",
        )
        follow_up_retry = prepare_satisfaction_follow_up(
            request_id,
            actor="operator:ci",
        )

        self.assertEqual(
            follow_up_retry["follow_up_id"],
            follow_up["follow_up_id"],
        )
        self.assertEqual(follow_up["status"], "prepared")
        self.assertEqual(follow_up["purpose"], "customer_satisfaction")
        self.assertEqual(follow_up["rating_min"], 1)
        self.assertEqual(follow_up["rating_max"], 5)
        self.assertIsNone(follow_up["destination_channel"])
        self.assertIsNone(follow_up["destination_address"])
        self.assertFalse(follow_up["response_recorded"])
        self.assertFalse(follow_up["sent"])
        self.assertFalse(follow_up["external_action_performed"])

        persisted_follow_up = get_satisfaction_follow_up(request_id)
        self.assertEqual(
            persisted_follow_up["follow_up_id"],
            follow_up["follow_up_id"],
        )

        satisfaction_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"]
            == "customer_satisfaction_follow_up_prepared"
        ]
        self.assertEqual(len(satisfaction_events), 1)
        self.assertFalse(
            satisfaction_events[0]["details"]["destination_resolved"]
        )
        self.assertFalse(
            satisfaction_events[0]["details"]["response_recorded"]
        )
        self.assertFalse(satisfaction_events[0]["details"]["sent"])
        self.assertFalse(
            satisfaction_events[0]["details"]["external_action_performed"]
        )

        responded_at = datetime.now(timezone.utc)
        response = record_satisfaction_response(
            request_id,
            UUID(follow_up["follow_up_id"]),
            rating=1,
            responded_at=responded_at,
            response_source="operator-recorded phone response",
            comment="Service had problems.",
            actor="operator:ci",
        )
        response_retry = record_satisfaction_response(
            request_id,
            UUID(follow_up["follow_up_id"]),
            rating=1,
            responded_at=responded_at,
            response_source="operator-recorded phone response",
            comment="Service had problems.",
            actor="operator:ci",
        )

        self.assertEqual(
            response_retry["follow_up_id"],
            response["follow_up_id"],
        )
        self.assertEqual(response["status"], "responded")
        self.assertEqual(response["rating"], 1)
        self.assertEqual(response["comment"], "Service had problems.")
        self.assertTrue(response["response_recorded"])
        self.assertFalse(response["sent"])
        self.assertFalse(response["external_action_performed"])

        with self.assertRaises(SatisfactionFollowUpConflictError):
            record_satisfaction_response(
                request_id,
                UUID(follow_up["follow_up_id"]),
                rating=2,
                responded_at=responded_at,
                response_source="operator-recorded phone response",
                comment="Different evidence",
                actor="operator:ci",
            )

        persisted_response = get_satisfaction_follow_up(request_id)
        self.assertEqual(persisted_response["status"], "responded")
        self.assertEqual(persisted_response["rating"], 1)

        response_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"]
            == "customer_satisfaction_response_recorded"
        ]
        self.assertEqual(len(response_events), 1)
        self.assertEqual(response_events[0]["details"]["rating"], 1)
        self.assertFalse(
            response_events[0]["details"]["review_request_created"]
        )
        self.assertFalse(
            response_events[0]["details"]["complaint_created"]
        )
        self.assertFalse(
            response_events[0]["details"]["rework_created"]
        )
        self.assertFalse(
            response_events[0]["details"]["external_action_performed"]
        )

        review_request = prepare_review_request(
            request_id,
            UUID(follow_up["follow_up_id"]),
            reason="Operator approved preparing a public review request.",
            actor="operator:ci",
        )
        review_retry = prepare_review_request(
            request_id,
            UUID(follow_up["follow_up_id"]),
            reason="Operator approved preparing a public review request.",
            actor="operator:ci",
        )

        self.assertEqual(
            review_retry["review_request_id"],
            review_request["review_request_id"],
        )
        self.assertEqual(review_request["status"], "prepared")
        self.assertFalse(review_request["rating_gated"])
        self.assertIsNone(review_request["target_platform"])
        self.assertIsNone(review_request["target_url"])
        self.assertIsNone(review_request["destination_channel"])
        self.assertIsNone(review_request["destination_address"])
        self.assertFalse(review_request["sent"])
        self.assertFalse(review_request["external_action_performed"])

        persisted_review = get_review_request(request_id)
        self.assertEqual(
            persisted_review["review_request_id"],
            review_request["review_request_id"],
        )

        review_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"] == "public_review_request_prepared"
        ]
        self.assertEqual(len(review_events), 1)
        self.assertEqual(
            review_events[0]["details"]["satisfaction_rating"],
            1,
        )
        self.assertFalse(review_events[0]["details"]["rating_gated"])
        self.assertFalse(review_events[0]["details"]["target_resolved"])
        self.assertFalse(
            review_events[0]["details"]["destination_resolved"]
        )
        self.assertFalse(review_events[0]["details"]["sent"])
        self.assertFalse(
            review_events[0]["details"]["external_action_performed"]
        )

        complaint = create_closure_escalation(
            request_id,
            UUID(follow_up["follow_up_id"]),
            "complaint",
            priority="high",
            reason="Customer reported service quality concerns.",
            actor="operator:ci",
        )
        complaint_retry = create_closure_escalation(
            request_id,
            UUID(follow_up["follow_up_id"]),
            "complaint",
            priority="high",
            reason="Customer reported service quality concerns.",
            actor="operator:ci",
        )
        rework = create_closure_escalation(
            request_id,
            UUID(follow_up["follow_up_id"]),
            "rework",
            priority="normal",
            reason="Operator wants rework reviewed before any new work is authorized.",
            actor="operator:ci",
        )
        rework_retry = create_closure_escalation(
            request_id,
            UUID(follow_up["follow_up_id"]),
            "rework",
            priority="normal",
            reason="Operator wants rework reviewed before any new work is authorized.",
            actor="operator:ci",
        )

        self.assertEqual(
            complaint_retry["escalation_id"],
            complaint["escalation_id"],
        )
        self.assertEqual(
            rework_retry["escalation_id"],
            rework["escalation_id"],
        )
        self.assertEqual(complaint["status"], "open")
        self.assertEqual(rework["status"], "open")
        self.assertEqual(complaint["escalation_kind"], "complaint")
        self.assertEqual(rework["escalation_kind"], "rework")

        for escalation in (complaint, rework):
            self.assertFalse(escalation["auto_triggered"])
            self.assertFalse(escalation["delivery_reopened"])
            self.assertFalse(escalation["rework_dispatched"])
            self.assertFalse(escalation["notification_sent"])
            self.assertFalse(escalation["external_action_performed"])

        persisted_escalations = get_closure_escalations(request_id)
        self.assertEqual(
            [item["escalation_kind"] for item in persisted_escalations],
            ["complaint", "rework"],
        )
        self.assertEqual(get_request(request_id)["status"], "actioned")
        self.assertEqual(get_delivery_status(request_id)["status"], "completed")

        escalation_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"] == "closure_escalation_created"
        ]
        self.assertEqual(len(escalation_events), 2)
        self.assertEqual(
            [event["details"]["escalation_kind"] for event in escalation_events],
            ["complaint", "rework"],
        )
        for event in escalation_events:
            self.assertEqual(event["details"]["satisfaction_rating"], 1)
            self.assertFalse(event["details"]["auto_triggered"])
            self.assertFalse(event["details"]["delivery_reopened"])
            self.assertFalse(event["details"]["rework_dispatched"])
            self.assertFalse(event["details"]["notification_sent"])
            self.assertFalse(
                event["details"]["external_action_performed"]
            )

        outcome = get_outcome_measurement(request_id)
        self.assertEqual(outcome["request_status"], "actioned")
        self.assertEqual(outcome["delivery_status"], "completed")
        self.assertTrue(outcome["delivery_completed"])
        self.assertEqual(outcome["satisfaction_status"], "responded")
        self.assertTrue(outcome["satisfaction_response_recorded"])
        self.assertEqual(outcome["satisfaction_rating"], 1)
        self.assertTrue(outcome["review_request_prepared"])
        self.assertEqual(outcome["delivery_exception_count"], 2)
        self.assertEqual(outcome["intervention_count"], 1)
        self.assertEqual(outcome["open_intervention_count"], 0)
        self.assertTrue(outcome["complaint_present"])
        self.assertTrue(outcome["rework_present"])
        self.assertIsNone(outcome["score"])
        self.assertIsNone(outcome["provider_rank"])
        self.assertFalse(outcome["policy_change_applied"])
        self.assertFalse(outcome["training_signal_applied"])
        self.assertFalse(outcome["external_action_performed"])

        request_created_event = next(
            event
            for event in get_request_events(request_id)
            if event["event_type"] == "request_created"
        )
        self.assertEqual(
            request_created_event["details"]["skill_versions"],
            {
                "request_intake": "1.0.0",
                "request_clarification": "1.0.0",
            },
        )

        evaluation = create_skill_evaluation(
            request_id,
            UUID(str(request_created_event["id"])),
            "request_intake",
            verdict="pass",
            notes=(
                "Human evaluator verified the recorded intake skill "
                "against the persisted real-case evidence."
            ),
            actor="operator:ci",
        )
        evaluation_retry = create_skill_evaluation(
            request_id,
            UUID(str(request_created_event["id"])),
            "request_intake",
            verdict="pass",
            notes=(
                "Human evaluator verified the recorded intake skill "
                "against the persisted real-case evidence."
            ),
            actor="operator:ci",
        )

        self.assertEqual(
            evaluation_retry["evaluation_id"],
            evaluation["evaluation_id"],
        )
        self.assertEqual(evaluation["skill_name"], "request_intake")
        self.assertEqual(evaluation["skill_version"], "1.0.0")
        self.assertEqual(evaluation["verdict"], "pass")
        self.assertEqual(
            evaluation["outcome_snapshot"]["satisfaction_rating"],
            1,
        )
        self.assertFalse(evaluation["training_signal_applied"])
        self.assertFalse(evaluation["skill_version_changed"])
        self.assertFalse(evaluation["policy_change_applied"])
        self.assertFalse(evaluation["promotion_applied"])
        self.assertFalse(evaluation["production_behaviour_changed"])

        with self.assertRaises(SkillEvaluationConflictError):
            create_skill_evaluation(
                request_id,
                UUID(str(request_created_event["id"])),
                "request_intake",
                verdict="fail",
                notes="Conflicting human verdict.",
                actor="operator:ci",
            )

        persisted_evaluations = get_skill_evaluations(request_id)
        self.assertEqual(len(persisted_evaluations), 1)
        self.assertEqual(
            persisted_evaluations[0]["evaluation_id"],
            evaluation["evaluation_id"],
        )

        evaluation_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"]
            == "skill_real_case_evaluation_recorded"
        ]
        self.assertEqual(len(evaluation_events), 1)
        self.assertEqual(
            evaluation_events[0]["details"]["skill_name"],
            "request_intake",
        )
        self.assertEqual(
            evaluation_events[0]["details"]["skill_version"],
            "1.0.0",
        )
        self.assertFalse(
            evaluation_events[0]["details"]["training_signal_applied"]
        )
        self.assertFalse(
            evaluation_events[0]["details"]["skill_version_changed"]
        )
        self.assertFalse(
            evaluation_events[0]["details"]["policy_change_applied"]
        )
        self.assertFalse(
            evaluation_events[0]["details"]["promotion_applied"]
        )
        self.assertFalse(
            evaluation_events[0]["details"][
                "production_behaviour_changed"
            ]
        )

        with self.assertRaises(SkillImprovementStateError):
            create_skill_improvement_proposal(
                request_id,
                UUID(evaluation["evaluation_id"]),
                change_scope="instructions",
                proposed_change=(
                    "Clarify that intake summaries must avoid unsupported "
                    "assumptions."
                ),
                rationale="Passing evaluations cannot directly create changes.",
                actor="operator:ci",
            )

        clarification_evaluation = create_skill_evaluation(
            request_id,
            UUID(str(request_created_event["id"])),
            "request_clarification",
            verdict="needs_review",
            notes=(
                "Human evaluator found the clarification behavior should "
                "better distinguish essential from optional details."
            ),
            actor="operator:ci",
        )

        proposal = create_skill_improvement_proposal(
            request_id,
            UUID(clarification_evaluation["evaluation_id"]),
            change_scope="instructions",
            proposed_change=(
                "Make essential-information checks explicitly distinguish "
                "blocking details from optional context before generating "
                "follow-up questions."
            ),
            rationale=(
                "The real-case evaluation identified a clarification gap, "
                "but this draft must remain unapplied until separately "
                "reviewed and regression-tested."
            ),
            actor="operator:ci",
        )
        proposal_retry = create_skill_improvement_proposal(
            request_id,
            UUID(clarification_evaluation["evaluation_id"]),
            change_scope="instructions",
            proposed_change=(
                "Make essential-information checks explicitly distinguish "
                "blocking details from optional context before generating "
                "follow-up questions."
            ),
            rationale=(
                "The real-case evaluation identified a clarification gap, "
                "but this draft must remain unapplied until separately "
                "reviewed and regression-tested."
            ),
            actor="operator:ci",
        )

        self.assertEqual(
            proposal_retry["proposal_id"],
            proposal["proposal_id"],
        )
        self.assertEqual(
            proposal["skill_name"],
            "request_clarification",
        )
        self.assertEqual(proposal["base_skill_version"], "1.0.0")
        self.assertEqual(proposal["status"], "proposed")
        self.assertFalse(proposal["applied"])
        self.assertFalse(proposal["skill_version_changed"])
        self.assertFalse(proposal["registry_changed"])
        self.assertFalse(proposal["policy_change_applied"])
        self.assertFalse(proposal["production_behaviour_changed"])

        with self.assertRaises(SkillImprovementConflictError):
            create_skill_improvement_proposal(
                request_id,
                UUID(clarification_evaluation["evaluation_id"]),
                change_scope="policy",
                proposed_change="Conflicting proposal.",
                rationale="Different evidence.",
                actor="operator:ci",
            )

        persisted_proposals = get_skill_improvement_proposals(
            request_id
        )
        self.assertEqual(len(persisted_proposals), 1)
        self.assertEqual(
            persisted_proposals[0]["proposal_id"],
            proposal["proposal_id"],
        )

        proposal_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"]
            == "skill_improvement_proposal_created"
        ]
        self.assertEqual(len(proposal_events), 1)
        self.assertEqual(
            proposal_events[0]["details"]["skill_name"],
            "request_clarification",
        )
        self.assertEqual(
            proposal_events[0]["details"]["base_skill_version"],
            "1.0.0",
        )
        self.assertFalse(proposal_events[0]["details"]["applied"])
        self.assertFalse(
            proposal_events[0]["details"]["skill_version_changed"]
        )
        self.assertFalse(
            proposal_events[0]["details"]["registry_changed"]
        )
        self.assertFalse(
            proposal_events[0]["details"]["policy_change_applied"]
        )
        self.assertFalse(
            proposal_events[0]["details"][
                "production_behaviour_changed"
            ]
        )


        passing_cases = [
            {
                "case_id": "clarification-target-existing-info",
                "purpose": "target",
                "baseline_result": "fail",
                "candidate_result": "pass",
                "notes": "Candidate stops asking for information already supplied.",
            },
            {
                "case_id": "clarification-regression-missing-location",
                "purpose": "regression",
                "baseline_result": "pass",
                "candidate_result": "pass",
                "notes": "Candidate still asks for genuinely required location.",
            },
        ]
        regression_test = record_skill_regression_test(
            request_id,
            UUID(proposal["proposal_id"]),
            suite_name="request-clarification-core",
            suite_version="1.0.0",
            cases=passing_cases,
            actor="operator:ci",
        )
        regression_retry = record_skill_regression_test(
            request_id,
            UUID(proposal["proposal_id"]),
            suite_name="request-clarification-core",
            suite_version="1.0.0",
            cases=passing_cases,
            actor="operator:ci",
        )

        self.assertEqual(
            regression_retry["regression_test_id"],
            regression_test["regression_test_id"],
        )
        self.assertEqual(regression_test["verdict"], "pass")
        self.assertTrue(regression_test["regression_gate_passed"])
        self.assertEqual(regression_test["target_cases"], 1)
        self.assertEqual(regression_test["fixed_target_cases"], 1)
        self.assertEqual(regression_test["regression_failures"], 0)
        self.assertFalse(regression_test["proposal_applied"])
        self.assertFalse(regression_test["skill_version_changed"])
        self.assertFalse(regression_test["registry_changed"])
        self.assertFalse(regression_test["promotion_applied"])
        self.assertFalse(
            regression_test["production_behaviour_changed"]
        )

        with self.assertRaises(SkillRegressionConflictError):
            record_skill_regression_test(
                request_id,
                UUID(proposal["proposal_id"]),
                suite_name="request-clarification-core",
                suite_version="1.0.0",
                cases=[
                    passing_cases[0],
                    {
                        **passing_cases[1],
                        "candidate_result": "fail",
                        "notes": "Conflicting regression evidence.",
                    },
                ],
                actor="operator:ci",
            )

        persisted_regression_tests = get_skill_regression_tests(request_id)
        self.assertEqual(len(persisted_regression_tests), 1)
        self.assertEqual(
            persisted_regression_tests[0]["regression_test_id"],
            regression_test["regression_test_id"],
        )

        regression_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"] == "skill_regression_test_recorded"
        ]
        self.assertEqual(len(regression_events), 1)
        self.assertEqual(
            regression_events[0]["details"]["verdict"],
            "pass",
        )
        self.assertTrue(
            regression_events[0]["details"]["regression_gate_passed"]
        )
        self.assertFalse(
            regression_events[0]["details"]["promotion_applied"]
        )
        self.assertFalse(
            regression_events[0]["details"][
                "production_behaviour_changed"
            ]
        )

        training_case = get_training_case(
            UUID(clarification_evaluation["evaluation_id"])
        )
        self.assertEqual(
            training_case["training_stage"],
            "ready_for_promotion_review",
        )
        self.assertEqual(
            training_case["proposal"]["proposal_id"],
            proposal["proposal_id"],
        )
        self.assertEqual(
            training_case["regression"]["regression_test_id"],
            regression_test["regression_test_id"],
        )
        self.assertEqual(training_case["supported_actions"], [])
        self.assertEqual(
            training_case["blocked_reason"],
            "promotion_not_supported",
        )
        self.assertFalse(training_case["promotion_supported"])
        self.assertFalse(
            training_case["production_behaviour_changed"]
        )

        promotion_ready_cases = list_training_cases(
            stage="ready_for_promotion_review",
            skill_name="request_clarification",
            limit=10,
        )
        self.assertEqual(len(promotion_ready_cases), 1)
        self.assertEqual(
            promotion_ready_cases[0]["evaluation_id"],
            clarification_evaluation["evaluation_id"],
        )


        safety_evaluation = create_skill_evaluation(
            request_id,
            UUID(str(request_created_event["id"])),
            "safety_triage",
            verdict="fail",
            notes="Safety triage wording needs revision after regression review.",
            actor="operator:ci",
        )
        safety_proposal = create_skill_improvement_proposal(
            request_id,
            UUID(safety_evaluation["evaluation_id"]),
            change_scope="instructions",
            proposed_change=(
                "Clarify the safety escalation criteria without widening "
                "ordinary-request escalation."
            ),
            rationale="Human evaluation identified an over-escalation risk.",
            actor="operator:ci",
        )
        failed_cases = [
            {
                "case_id": "safety-target-over-escalation",
                "purpose": "target",
                "baseline_result": "fail",
                "candidate_result": "pass",
                "notes": "Target failure was corrected.",
            },
            {
                "case_id": "safety-regression-dangerous-request",
                "purpose": "regression",
                "baseline_result": "pass",
                "candidate_result": "fail",
                "notes": "Candidate broke a known dangerous-request escalation.",
            },
        ]
        failed_regression = record_skill_regression_test(
            request_id,
            UUID(safety_proposal["proposal_id"]),
            suite_name="safety-triage-core",
            suite_version="1.0.0",
            cases=failed_cases,
            actor="operator:ci",
        )
        self.assertEqual(failed_regression["verdict"], "fail")

        failed_training_case = get_training_case(
            UUID(safety_evaluation["evaluation_id"])
        )
        self.assertEqual(
            failed_training_case["training_stage"],
            "regression_failed",
        )
        self.assertEqual(
            failed_training_case["supported_actions"],
            ["create_improvement_revision"],
        )
        self.assertIsNone(failed_training_case["blocked_reason"])

        revision = create_skill_improvement_revision(
            request_id,
            UUID(safety_proposal["proposal_id"]),
            proposed_change=(
                "Escalate urgent or dangerous requests while explicitly "
                "excluding ordinary requests whose only issue is missing details."
            ),
            rationale=(
                "The first candidate fixed over-escalation but regressed a "
                "dangerous-request case."
            ),
            actor="operator:ci",
        )
        revision_retry = create_skill_improvement_revision(
            request_id,
            UUID(safety_proposal["proposal_id"]),
            proposed_change=(
                "Escalate urgent or dangerous requests while explicitly "
                "excluding ordinary requests whose only issue is missing details."
            ),
            rationale=(
                "The first candidate fixed over-escalation but regressed a "
                "dangerous-request case."
            ),
            actor="operator:ci",
        )
        self.assertEqual(
            revision_retry["revision_id"],
            revision["revision_id"],
        )
        self.assertEqual(revision["revision_number"], 1)
        self.assertFalse(revision["applied"])
        self.assertFalse(revision["promotion_applied"])

        with self.assertRaises(SkillRevisionConflictError):
            create_skill_improvement_revision(
                request_id,
                UUID(safety_proposal["proposal_id"]),
                proposed_change="Conflicting revision while awaiting regression.",
                rationale="Different evidence.",
                actor="operator:ci",
            )

        revised_pending_case = get_training_case(
            UUID(safety_evaluation["evaluation_id"])
        )
        self.assertEqual(
            revised_pending_case["training_stage"],
            "needs_regression_test",
        )
        self.assertEqual(
            revised_pending_case["revision"]["revision_id"],
            revision["revision_id"],
        )

        revised_cases = [
            {
                "case_id": "safety-target-over-escalation",
                "purpose": "target",
                "baseline_result": "fail",
                "candidate_result": "pass",
                "notes": "Target remains fixed.",
            },
            {
                "case_id": "safety-regression-dangerous-request",
                "purpose": "regression",
                "baseline_result": "pass",
                "candidate_result": "pass",
                "notes": "Dangerous-request escalation is preserved.",
            },
        ]
        revised_regression = record_skill_regression_test(
            request_id,
            UUID(safety_proposal["proposal_id"]),
            revision_id=UUID(revision["revision_id"]),
            suite_name="safety-triage-core",
            suite_version="1.0.1",
            cases=revised_cases,
            actor="operator:ci",
        )
        self.assertEqual(revised_regression["verdict"], "pass")
        self.assertEqual(
            revised_regression["revision_id"],
            revision["revision_id"],
        )

        persisted_revisions = get_skill_improvement_revisions(request_id)
        self.assertEqual(len(persisted_revisions), 1)
        self.assertEqual(
            persisted_revisions[0]["revision_id"],
            revision["revision_id"],
        )

        revised_ready_case = get_training_case(
            UUID(safety_evaluation["evaluation_id"])
        )
        self.assertEqual(
            revised_ready_case["training_stage"],
            "ready_for_promotion_review",
        )
        self.assertEqual(
            revised_ready_case["regression"]["revision_id"],
            revision["revision_id"],
        )
        self.assertEqual(
            revised_ready_case["blocked_reason"],
            "promotion_not_supported",
        )
        self.assertFalse(revised_ready_case["promotion_supported"])

        revision_events = [
            event
            for event in get_request_events(request_id)
            if event["event_type"] == "skill_improvement_revision_created"
        ]
        self.assertEqual(len(revision_events), 1)
        self.assertFalse(
            revision_events[0]["details"]["promotion_applied"]
        )
        self.assertFalse(
            revision_events[0]["details"][
                "production_behaviour_changed"
            ]
        )


if __name__ == "__main__":
    unittest.main()
