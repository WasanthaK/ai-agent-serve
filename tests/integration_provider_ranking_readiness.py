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
from provider_ranking_readiness import (
    assess_response_reliability_ranking_readiness,
)
from provider_response_reliability import (
    record_provider_response,
    record_response_opportunity,
)


class ProviderRankingReadinessIntegrationTests(unittest.TestCase):
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

    def add_completed_history(self, provider_id, as_of, count):
        for index in range(count):
            opportunity_id = uuid4()
            offered_at = as_of - timedelta(days=20 - index)
            deadline_at = offered_at + timedelta(hours=24)
            record_response_opportunity(
                provider_id,
                opportunity_id,
                offered_at,
                deadline_at,
            )
            record_provider_response(
                provider_id,
                opportunity_id,
                "quote" if index % 2 == 0 else "decline",
                offered_at + timedelta(hours=2),
            )

    def test_real_history_blocks_then_allows_ranking_readiness(self):
        first = self.create_eligible_provider("CI Ranking Ready A")
        second = self.create_eligible_provider("CI Ranking Ready B")
        as_of = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)

        self.add_completed_history(first, as_of, 5)
        self.add_completed_history(second, as_of, 4)

        blocked = assess_response_reliability_ranking_readiness(
            "plumbing",
            "bn:brunei-muara",
            as_of=as_of,
        )

        self.assertEqual(blocked["candidate_count"], 2)
        self.assertEqual(blocked["status"], "insufficient_history")
        self.assertFalse(blocked["ranking_implementation_ready"])
        self.assertFalse(blocked["ranking_policy_enabled"])
        self.assertFalse(blocked["ranked"])
        self.assertEqual(
            blocked["insufficient_history_provider_ids"],
            [str(second)],
        )

        self.add_completed_history(second, as_of, 1)

        ready = assess_response_reliability_ranking_readiness(
            "plumbing",
            "bn:brunei-muara",
            as_of=as_of,
        )

        self.assertEqual(
            ready["status"],
            "ready_for_ranking_implementation",
        )
        self.assertTrue(ready["ranking_implementation_ready"])
        self.assertFalse(ready["ranking_policy_enabled"])
        self.assertFalse(ready["ranked"])
        self.assertIsNone(ready["selected_provider_id"])
        self.assertEqual(
            {item["provider_id"] for item in ready["evidence"]},
            {str(first), str(second)},
        )
        self.assertTrue(all(
            item["history_status"] == "sufficient_history"
            for item in ready["evidence"]
        ))


if __name__ == "__main__":
    unittest.main()
