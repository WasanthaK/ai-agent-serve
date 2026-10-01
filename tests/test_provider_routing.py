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

    def test_explanation_uses_only_deterministic_candidate_evidence(self):
        provider_id = uuid4()
        candidate_result = {
            "status": "eligible_candidates",
            "service_slug": "plumbing",
            "area_key": "bn:brunei-muara",
            "eligibility_basis": list(provider_routing.ELIGIBILITY_BASIS),
            "candidates": [
                {
                    "provider_id": str(provider_id),
                    "display_name": "Explained Provider",
                }
            ],
            "candidate_count": 1,
            "requires_human_review": False,
        }

        with patch.object(
            provider_routing,
            "build_provider_candidates",
            return_value=candidate_result,
        ) as builder:
            result = provider_routing.explain_provider_candidates(
                "plumbing",
                "bn:brunei-muara",
            )

        builder.assert_called_once_with("plumbing", "bn:brunei-muara")
        self.assertEqual(result["status"], "eligible_candidates")
        self.assertEqual(result["candidate_count"], 1)
        self.assertFalse(result["ranked"])
        self.assertIsNone(result["selected_provider_id"])
        self.assertFalse(result["requires_human_review"])
        self.assertEqual(
            [reason["code"] for reason in result["candidates"][0]["eligibility_reasons"]],
            list(provider_routing.ELIGIBILITY_BASIS),
        )
        self.assertEqual(
            result["candidates"][0]["display_name"],
            "Explained Provider",
        )

    def test_no_candidate_explanation_is_generic_and_escalates(self):
        candidate_result = {
            "status": "no_eligible_provider",
            "service_slug": "plumbing",
            "area_key": "bn:brunei-muara",
            "eligibility_basis": list(provider_routing.ELIGIBILITY_BASIS),
            "candidates": [],
            "candidate_count": 0,
            "requires_human_review": True,
        }

        with patch.object(
            provider_routing,
            "build_provider_candidates",
            return_value=candidate_result,
        ):
            result = provider_routing.explain_provider_candidates(
                "plumbing",
                "bn:brunei-muara",
            )

        self.assertEqual(result["status"], "no_eligible_provider")
        self.assertEqual(result["candidates"], [])
        self.assertEqual(
            result["explanation"]["code"],
            "no_provider_met_all_requirements",
        )
        self.assertFalse(result["ranked"])
        self.assertIsNone(result["selected_provider_id"])
        self.assertTrue(result["requires_human_review"])
        explanation = result["explanation"]["detail"].lower()
        self.assertNotIn("nearest", explanation)
        self.assertNotIn("best", explanation)
        self.assertNotIn("failed compliance", explanation)


if __name__ == "__main__":
    unittest.main()
