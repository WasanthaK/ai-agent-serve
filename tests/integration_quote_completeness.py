import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from db import get_connection, save_request
from provider_directory import (
    add_provider_coverage_area,
    add_provider_service_capability,
    create_provider,
    set_provider_availability,
    set_provider_compliance,
)
from provider_selection import select_providers_for_request
from quote_completeness import assess_quote_completeness
from quote_normalization import normalize_structured_quote
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


class QuoteCompletenessIntegrationTests(unittest.TestCase):
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

    def create_quote(self, *, exclusions, terms, validity_expires_at=None):
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
            "CI Completeness Provider",
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
        ingest_rfq_response(
            request_id,
            handoff_id,
            "quote",
            datetime.now(timezone.utc),
            actor="operator:ci",
        )
        normalize_structured_quote(
            request_id,
            handoff_id,
            amount_minor=125000,
            currency="AUD",
            scope_summary="Supply and replace leaking kitchen tap.",
            exclusions=exclusions,
            terms=terms,
            validity_expires_at=validity_expires_at,
            actor="operator:ci",
        )
        return request_id, handoff_id

    def test_persisted_quote_completeness_is_deterministic(self):
        as_of = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
        request_id, handoff_id = self.create_quote(
            exclusions=["Wall repairs"],
            terms=["Payment on completion"],
            validity_expires_at=as_of + timedelta(days=7),
        )

        result = assess_quote_completeness(
            request_id,
            handoff_id,
            as_of=as_of,
        )

        self.assertEqual(result["status"], "complete")
        self.assertTrue(result["comparison_ready"])
        self.assertEqual(result["missing_required_fields"], [])
        self.assertEqual(result["blocking_reasons"], [])
        self.assertFalse(result["evaluated"])
        self.assertFalse(result["recommended"])
        self.assertFalse(result["selected"])

    def test_missing_required_commercial_disclosures_block_comparison(self):
        as_of = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
        request_id, handoff_id = self.create_quote(
            exclusions=[],
            terms=[],
        )

        result = assess_quote_completeness(
            request_id,
            handoff_id,
            as_of=as_of,
        )

        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["comparison_ready"])
        self.assertEqual(
            result["missing_required_fields"],
            ["exclusions", "terms"],
        )


if __name__ == "__main__":
    unittest.main()
