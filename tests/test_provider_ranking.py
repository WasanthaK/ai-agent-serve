import unittest
from unittest.mock import patch

import provider_ranking as ranking


class ProviderRankingTests(unittest.TestCase):
    def test_not_ready_fails_closed(self):
        with patch.object(
            ranking,
            "assess_response_reliability_ranking_readiness",
            return_value={
                "ranking_implementation_ready": False,
                "readiness_reason": "insufficient history",
            },
        ):
            with self.assertRaises(ranking.ProviderRankingNotReadyError):
                ranking.rank_providers_by_response_reliability(
                    "plumbing",
                    "bn:brunei-muara",
                )

    def test_orders_by_reliability_without_selecting(self):
        readiness = {
            "ranking_implementation_ready": True,
            "readiness_reason": "ready",
            "evidence": [
                {
                    "provider_id": "11111111-1111-1111-1111-111111111111",
                    "display_name": "Provider A",
                    "completed_opportunities": 5,
                    "reliability_bps": 8000,
                },
                {
                    "provider_id": "22222222-2222-2222-2222-222222222222",
                    "display_name": "Provider B",
                    "completed_opportunities": 6,
                    "reliability_bps": 9000,
                },
            ],
        }

        with patch.object(
            ranking,
            "assess_response_reliability_ranking_readiness",
            return_value=readiness,
        ):
            result = ranking.rank_providers_by_response_reliability(
                "plumbing",
                "bn:brunei-muara",
            )

        self.assertTrue(result["ranked"])
        self.assertEqual(
            [item["provider_id"] for item in result["ranked_candidates"]],
            [
                "22222222-2222-2222-2222-222222222222",
                "11111111-1111-1111-1111-111111111111",
            ],
        )
        self.assertIsNone(result["selected_provider_id"])
        self.assertEqual(result["selection_mode"], "human_only")
        self.assertFalse(result["requires_human_review"])

    def test_ties_share_rank_and_require_human_review(self):
        readiness = {
            "ranking_implementation_ready": True,
            "readiness_reason": "ready",
            "evidence": [
                {
                    "provider_id": "11111111-1111-1111-1111-111111111111",
                    "display_name": "Provider A",
                    "completed_opportunities": 5,
                    "reliability_bps": 9000,
                },
                {
                    "provider_id": "22222222-2222-2222-2222-222222222222",
                    "display_name": "Provider B",
                    "completed_opportunities": 8,
                    "reliability_bps": 9000,
                },
            ],
        }

        with patch.object(
            ranking,
            "assess_response_reliability_ranking_readiness",
            return_value=readiness,
        ):
            result = ranking.rank_providers_by_response_reliability(
                "plumbing",
                "bn:brunei-muara",
            )

        self.assertTrue(result["has_ties"])
        self.assertTrue(result["requires_human_review"])
        self.assertEqual(
            [item["rank_position"] for item in result["ranked_candidates"]],
            [1, 1],
        )
        self.assertTrue(all(
            item["tied"] for item in result["ranked_candidates"]
        ))
        self.assertIsNone(result["selected_provider_id"])


if __name__ == "__main__":
    unittest.main()
