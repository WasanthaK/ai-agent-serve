import unittest
from uuid import uuid4

from db import get_connection, get_request_events, save_request
from provider_directory import (
    add_provider_coverage_area,
    add_provider_service_capability,
    create_provider,
    set_provider_availability,
    set_provider_compliance,
)
from provider_selection import (
    ProviderSelectionConflictError,
    ProviderSelectionEligibilityError,
    ProviderSelectionStateError,
    get_provider_selection,
    select_providers_for_request,
)


def ready_analysis():
    return {
        "intent": "Request a quote",
        "category": "plumbing",
        "summary": "Need plumbing work",
        "urgency": "normal",
        "next_action": "Route to suitable providers",
        "needs_human_review": False,
        "missing_information": [],
        "follow_up_questions": [],
    }


def needs_information_analysis():
    result = ready_analysis()
    result["missing_information"] = ["location"]
    result["follow_up_questions"] = ["What is the service location?"]
    return result


class ProviderSelectionIntegrationTests(unittest.TestCase):
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

    def create_request(self, analysis=None):
        request_id = save_request(
            "website",
            "Selection Test Customer",
            "Need a plumber",
            analysis or ready_analysis(),
        )
        self.request_ids.append(request_id)
        return request_id

    def create_provider(self, name, *, compliant=True):
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
        set_provider_compliance(
            provider_id,
            "compliant" if compliant else "non_compliant",
        )
        return provider_id

    def test_human_selection_uses_current_eligible_snapshot_and_is_immutable(self):
        request_id = self.create_request()
        first = self.create_provider("CI Selection Provider A")
        second = self.create_provider("CI Selection Provider B")
        ineligible = self.create_provider(
            "CI Selection Noncompliant Provider",
            compliant=False,
        )

        selection = select_providers_for_request(
            request_id,
            "plumbing",
            "bn:brunei-muara",
            [second, first],
            actor="operator:ci",
            reason="Human selected both eligible providers for RFQ preparation",
        )

        expected_selected = sorted([str(first), str(second)])
        expected_eligible = sorted([str(first), str(second)])

        self.assertEqual(selection["selected_provider_ids"], expected_selected)
        self.assertEqual(selection["eligible_provider_ids"], expected_eligible)
        self.assertEqual(selection["selection_authority"], "human")
        self.assertFalse(selection["ranked"])
        self.assertEqual(selection["selected_by"], "operator:ci")
        self.assertNotIn(str(ineligible), selection["eligible_provider_ids"])

        persisted = get_provider_selection(request_id)
        self.assertEqual(persisted["selection_id"], selection["selection_id"])
        self.assertEqual(persisted["selected_provider_ids"], expected_selected)

        events = get_request_events(request_id)
        selection_events = [
            event for event in events
            if event["event_type"] == "provider_selection_recorded"
        ]
        self.assertEqual(len(selection_events), 1)
        event = selection_events[0]
        self.assertEqual(event["actor"], "operator:ci")
        self.assertEqual(
            event["details"]["selected_provider_ids"],
            expected_selected,
        )
        self.assertEqual(
            event["details"]["eligible_provider_ids"],
            expected_eligible,
        )
        self.assertFalse(event["details"]["ranked"])
        self.assertEqual(event["details"]["selection_authority"], "human")

        # The immutable decision remains idempotent even if eligibility changes later.
        set_provider_availability(first, "unavailable")
        retry = select_providers_for_request(
            request_id,
            "plumbing",
            "bn:brunei-muara",
            [first, second],
            actor="operator:ci",
            reason="Human selected both eligible providers for RFQ preparation",
        )
        self.assertEqual(retry["selection_id"], selection["selection_id"])

        with self.assertRaises(ProviderSelectionConflictError):
            select_providers_for_request(
                request_id,
                "plumbing",
                "bn:brunei-muara",
                [second],
                actor="operator:ci",
                reason="Different selection",
            )

        events_after_retry = get_request_events(request_id)
        self.assertEqual(
            len([
                event for event in events_after_retry
                if event["event_type"] == "provider_selection_recorded"
            ]),
            1,
        )

    def test_ineligible_provider_is_rejected_without_persisting_selection(self):
        request_id = self.create_request()
        eligible = self.create_provider("CI Eligible Provider")
        ineligible = self.create_provider(
            "CI Ineligible Provider",
            compliant=False,
        )

        with self.assertRaises(ProviderSelectionEligibilityError):
            select_providers_for_request(
                request_id,
                "plumbing",
                "bn:brunei-muara",
                [eligible, ineligible],
                actor="operator:ci",
            )

        self.assertIsNone(get_provider_selection(request_id))
        self.assertFalse(any(
            event["event_type"] == "provider_selection_recorded"
            for event in get_request_events(request_id)
        ))

    def test_non_actionable_request_cannot_select_providers(self):
        request_id = self.create_request(needs_information_analysis())
        provider_id = self.create_provider("CI State Guard Provider")

        with self.assertRaises(ProviderSelectionStateError):
            select_providers_for_request(
                request_id,
                "plumbing",
                "bn:brunei-muara",
                [provider_id],
                actor="operator:ci",
            )

        self.assertIsNone(get_provider_selection(request_id))


if __name__ == "__main__":
    unittest.main()
