import unittest
from datetime import date, datetime, timedelta, timezone
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
from quote_comparison import compare_request_quotes
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


class QuoteComparisonIntegrationTests(unittest.TestCase):
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

    def test_compares_ready_quotes_without_recommendation(self):
        request_id = save_request(
            "website",
            "CI Customer",
            "Need plumbing work",
            ready_analysis(),
        )
        self.request_ids.append(request_id)

        first = self.create_provider("CI Quote Compare A")
        second = self.create_provider("CI Quote Compare B")

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

        comparison_as_of = None

        for provider_id, amount, available, duration in (
            (first, 120000, date(2026, 10, 8), 2),
            (second, 100000, date(2026, 10, 10), 1),
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
            normalize_structured_quote(
                request_id,
                handoff_id,
                amount_minor=amount,
                currency="AUD",
                scope_summary="Supply and replace leaking kitchen tap.",
                exclusions=["Wall repairs"],
                terms=["Payment on completion"],
                available_from=available,
                estimated_duration_days=duration,
                validity_expires_at=responded_at + timedelta(days=14),
                actor="operator:ci",
            )

        result = compare_request_quotes(
            request_id,
            as_of=comparison_as_of,
        )

        self.assertEqual(result["quote_count"], 2)
        self.assertTrue(result["price_comparable"])
        self.assertTrue(result["availability_comparable"])
        self.assertTrue(result["duration_comparable"])
        self.assertEqual(result["comparison_gaps"], [])
        self.assertFalse(result["requires_human_review"])

        by_provider = {
            item["provider_id"]: item["normalized_quote_id"]
            for item in result["quotes"]
        }
        self.assertEqual(
            result["lowest_price_quote_ids"],
            [by_provider[str(second)]],
        )
        self.assertEqual(
            result["earliest_available_quote_ids"],
            [by_provider[str(first)]],
        )
        self.assertEqual(
            result["shortest_duration_quote_ids"],
            [by_provider[str(second)]],
        )
        self.assertIsNone(result["overall_winner_quote_id"])
        self.assertIsNone(result["recommended_quote_id"])
        self.assertIsNone(result["selected_quote_id"])


if __name__ == "__main__":
    unittest.main()
