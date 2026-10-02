import unittest
from unittest.mock import patch
from uuid import uuid4

import provider_ranking_readiness as readiness


def metric(provider_id, *, status, completed, score):
    return {
        "provider_id": str(provider_id),
        "factor": "response_reliability",
        "status": status,
        "window_days": 90,
        "minimum_completed_opportunities": 5,
        "completed_opportunities": completed,
        "on_time_responses": completed if score == 10000 else 0,
        "late_responses": 0,
        "no_responses": 0,
        "reliability_bps": score,
    }


class ProviderRankingReadinessTests(unittest.TestCase):
    def test_single_candidate_is_not_rankable_even_with_sufficient_history(self):
        provider_id = uuid4()
        candidates = {
            "status": "eligible_candidates",
            "service_slug": "plumbing",
            "area_key": "bn:brunei-muara",
            "candidates": [{
                "provider_id": str(provider_id),
                "display_name": "Provider A",
            }],
            "candidate_count": 1,
        }

        with patch.object(
            readiness,
            "build_provider_candidates",
            return_value=candidates,
        ), patch.object(
            readiness,
            "calculate_provider_response_reliability",
            return_value=metric(
                provider_id,
                status="sufficient_history",
                completed=5,
                score=10000,
            ),
        ):
            result = readiness.assess_response_reliability_ranking_readiness(
                "plumbing",
                "bn:brunei-muara",
            )

        self.assertEqual(result["status"], "insufficient_candidates")
        self.assertFalse(result["ranking_implementation_ready"])
        self.assertFalse(result["ranking_policy_enabled"])
        self.assertFalse(result["ranked"])
        self.assertIsNone(result["selected_provider_id"])

    def test_one_insufficient_provider_blocks_whole_candidate_set(self):
        first = uuid4()
        second = uuid4()
        candidates = {
            "status": "eligible_candidates",
            "service_slug": "plumbing",
            "area_key": "bn:brunei-muara",
            "candidates": [
                {"provider_id": str(first), "display_name": "Provider A"},
                {"provider_id": str(second), "display_name": "Provider B"},
            ],
            "candidate_count": 2,
        }

        def reliability(provider_id, as_of=None):
            if provider_id == first:
                return metric(
                    first,
                    status="sufficient_history",
                    completed=6,
                    score=8333,
                )
            return metric(
                second,
                status="insufficient_history",
                completed=4,
                score=None,
            )

        with patch.object(
            readiness,
            "build_provider_candidates",
            return_value=candidates,
        ), patch.object(
            readiness,
            "calculate_provider_response_reliability",
            side_effect=reliability,
        ):
            result = readiness.assess_response_reliability_ranking_readiness(
                "plumbing",
                "bn:brunei-muara",
            )

        self.assertEqual(result["status"], "insufficient_history")
        self.assertEqual(
            result["insufficient_history_provider_ids"],
            [str(second)],
        )
        self.assertFalse(result["ranking_implementation_ready"])
        self.assertFalse(result["ranked"])

    def test_all_candidates_with_sufficient_history_only_marks_readiness(self):
        provider_ids = [uuid4(), uuid4()]
        candidates = {
            "status": "eligible_candidates",
            "service_slug": "plumbing",
            "area_key": "bn:brunei-muara",
            "candidates": [
                {
                    "provider_id": str(provider_id),
                    "display_name": f"Provider {index}",
                }
                for index, provider_id in enumerate(provider_ids)
            ],
            "candidate_count": 2,
        }

        with patch.object(
            readiness,
            "build_provider_candidates",
            return_value=candidates,
        ), patch.object(
            readiness,
            "calculate_provider_response_reliability",
            side_effect=[
                metric(
                    provider_ids[0],
                    status="sufficient_history",
                    completed=5,
                    score=8000,
                ),
                metric(
                    provider_ids[1],
                    status="sufficient_history",
                    completed=7,
                    score=9000,
                ),
            ],
        ):
            result = readiness.assess_response_reliability_ranking_readiness(
                "plumbing",
                "bn:brunei-muara",
            )

        self.assertEqual(
            result["status"],
            "ready_for_ranking_implementation",
        )
        self.assertTrue(result["ranking_implementation_ready"])
        self.assertFalse(result["ranking_policy_enabled"])
        self.assertFalse(result["ranked"])
        self.assertIsNone(result["selected_provider_id"])
        self.assertEqual(
            [item["reliability_bps"] for item in result["evidence"]],
            [8000, 9000],
        )


if __name__ == "__main__":
    unittest.main()
