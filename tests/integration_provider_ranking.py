import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from db import get_connection
from provider_directory import (
    add_provider_coverage_area,
    add_provider_service_capability,
    create_provider,
    set_provider_availability,
    set_provider_compliance,
)
from provider_ranking import rank_providers_by_response_reliability
from provider_response_reliability import (
    record_provider_response,
    record_response_opportunity,
)


class ProviderRankingIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.provider_ids = []

    def tearDown(self):
        with get_connection() as conn:
            with conn.cursor() as cur:
                if self.provider_ids:
                    cur.execute(
                        "DELETE FROM providers WHERE id = ANY(%s)",
                        (self.provider_ids,),
                    )

    def create_provider(self, name):
        provider_id = uuid4()
        self.provider_ids.append(provider_id)
        create_provider(name, approval_status="approved", provider_id=provider_id)
        add_provider_service_capability(provider_id, "plumbing")
        add_provider_coverage_area(provider_id, "bn:brunei-muara")
        set_provider_availability(provider_id, "available")
        set_provider_compliance(provider_id, "compliant")
        return provider_id

    def add_history(self, provider_id, as_of, on_time_count, total_count):
        for index in range(total_count):
            opportunity_id = uuid4()
            offered_at = as_of - timedelta(days=20 - index)
            deadline = offered_at + timedelta(hours=24)
            record_response_opportunity(
                provider_id,
                opportunity_id,
                offered_at,
                deadline,
            )
            if index < on_time_count:
                responded_at = offered_at + timedelta(hours=2)
            else:
                responded_at = offered_at + timedelta(hours=30)
            record_provider_response(
                provider_id,
                opportunity_id,
                "quote",
                responded_at,
            )

    def test_ranks_by_governed_reliability_and_never_selects(self):
        as_of = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
        first = self.create_provider("CI Rank A")
        second = self.create_provider("CI Rank B")

        self.add_history(first, as_of, on_time_count=4, total_count=5)
        self.add_history(second, as_of, on_time_count=5, total_count=5)

        result = rank_providers_by_response_reliability(
            "plumbing",
            "bn:brunei-muara",
            as_of=as_of,
        )

        self.assertTrue(result["ranked"])
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(
            [item["provider_id"] for item in result["ranked_candidates"]],
            [str(second), str(first)],
        )
        self.assertEqual(
            [item["response_reliability_bps"] for item in result["ranked_candidates"]],
            [10000, 8000],
        )
        self.assertIsNone(result["selected_provider_id"])
        self.assertEqual(result["selection_mode"], "human_only")
        self.assertFalse(result["has_ties"])


if __name__ == "__main__":
    unittest.main()
