import unittest
from uuid import uuid4

from db import get_connection
from provider_directory import (
    add_provider_coverage_area,
    add_provider_service_capability,
    create_provider,
    set_provider_availability,
    set_provider_compliance,
)
from provider_routing import build_provider_candidates, explain_provider_candidates


class ProviderRoutingIntegrationTests(unittest.TestCase):
    def test_routing_candidates_use_full_persisted_eligibility(self):
        eligible_id = uuid4()
        noncompliant_id = uuid4()

        for provider_id, name in (
            (eligible_id, "CI Eligible Routing Provider"),
            (noncompliant_id, "CI Noncompliant Routing Provider"),
        ):
            create_provider(name, approval_status="approved", provider_id=provider_id)
            add_provider_service_capability(provider_id, "plumbing")
            add_provider_coverage_area(provider_id, "bn:brunei-muara")
            set_provider_availability(provider_id, "available")

        set_provider_compliance(eligible_id, "compliant")
        set_provider_compliance(noncompliant_id, "non_compliant")

        try:
            result = build_provider_candidates(
                "plumbing",
                "bn:brunei-muara",
            )

            self.assertEqual(result["status"], "eligible_candidates")
            self.assertEqual(result["candidate_count"], 1)
            self.assertEqual(
                result["candidates"],
                [
                    {
                        "provider_id": str(eligible_id),
                        "display_name": "CI Eligible Routing Provider",
                    }
                ],
            )
            self.assertFalse(result["requires_human_review"])

            explained = explain_provider_candidates(
                "plumbing",
                "bn:brunei-muara",
            )
            self.assertEqual(explained["candidate_count"], 1)
            self.assertFalse(explained["ranked"])
            self.assertIsNone(explained["selected_provider_id"])
            self.assertEqual(
                explained["candidates"][0]["provider_id"],
                str(eligible_id),
            )
            self.assertEqual(
                [
                    reason["code"]
                    for reason in explained["candidates"][0]["eligibility_reasons"]
                ],
                [
                    "approved",
                    "service_capability",
                    "exact_coverage_area",
                    "available",
                    "compliant",
                ],
            )
        finally:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM providers WHERE id IN (%s, %s)",
                        (eligible_id, noncompliant_id),
                    )


if __name__ == "__main__":
    unittest.main()
