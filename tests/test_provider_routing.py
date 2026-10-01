import unittest
from unittest.mock import patch
from uuid import uuid4

import provider_routing


class ProviderRoutingTests(unittest.TestCase):
    def test_builds_unranked_candidates_from_eligible_provider_set(self):
        first_id = uuid4()
        second_id = uuid4()
        eligible = [
            {"id": first_id, "display_name": "First Provider"},
            {"id": second_id, "display_name": "Second Provider"},
        ]

        with patch.object(
            provider_routing,
            "list_eligible_providers_for_service_and_area",
            return_value=eligible,
        ) as lookup:
            result = provider_routing.build_provider_candidates(
                "plumbing",
                "bn:brunei-muara",
            )

        lookup.assert_called_once_with("plumbing", "bn:brunei-muara")
        self.assertEqual(result["status"], "eligible_candidates")
        self.assertEqual(result["candidate_count"], 2)
        self.assertFalse(result["requires_human_review"])
        self.assertEqual(
            result["candidates"],
            [
                {
                    "provider_id": str(first_id),
                    "display_name": "First Provider",
                },
                {
                    "provider_id": str(second_id),
                    "display_name": "Second Provider",
                },
            ],
        )
        self.assertEqual(
            result["eligibility_basis"],
            [
                "approved",
                "service_capability",
                "exact_coverage_area",
                "available",
                "compliant",
            ],
        )

    def test_empty_eligible_set_escalates_without_broadening(self):
        with patch.object(
            provider_routing,
            "list_eligible_providers_for_service_and_area",
            return_value=[],
        ) as lookup:
            result = provider_routing.build_provider_candidates(
                "plumbing",
                "bn:brunei-muara",
            )

        lookup.assert_called_once_with("plumbing", "bn:brunei-muara")
        self.assertEqual(result["status"], "no_eligible_provider")
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["candidates"], [])
        self.assertTrue(result["requires_human_review"])

    def test_provider_fields_outside_routing_contract_are_not_exposed(self):
        provider_id = uuid4()
        eligible = [
            {
                "id": provider_id,
                "display_name": "Safe Provider",
                "approval_status": "approved",
                "internal_note": "must not leak",
            }
        ]

        with patch.object(
            provider_routing,
            "list_eligible_providers_for_service_and_area",
            return_value=eligible,
        ):
            result = provider_routing.build_provider_candidates(
                "plumbing",
                "bn:brunei-muara",
            )

        self.assertEqual(
            result["candidates"],
            [{"provider_id": str(provider_id), "display_name": "Safe Provider"}],
        )


if __name__ == "__main__":
    unittest.main()
