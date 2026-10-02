import unittest
from unittest.mock import patch
from uuid import UUID

import quote_recommendation as recommendation


class QuoteRecommendationTests(unittest.TestCase):
    def test_requires_operator_actor(self):
        with self.assertRaises(
            recommendation.QuoteRecommendationValidationError
        ):
            recommendation.recommend_quote_for_request(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                rationale="Best fit",
                actor="model:quote-evaluation",
            )

    def test_rationale_is_required(self):
        with self.assertRaises(
            recommendation.QuoteRecommendationValidationError
        ):
            recommendation.recommend_quote_for_request(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                rationale=" ",
                actor="operator:test",
            )

    def test_quote_must_be_in_current_ready_comparison_set(self):
        comparison = {
            "quotes": [{
                "normalized_quote_id":
                    "33333333-3333-3333-3333-333333333333"
            }]
        }
        with patch.object(
            recommendation,
            "compare_request_quotes",
            return_value=comparison,
        ):
            with self.assertRaises(
                recommendation.QuoteRecommendationEligibilityError
            ):
                recommendation.recommend_quote_for_request(
                    UUID("11111111-1111-1111-1111-111111111111"),
                    UUID("22222222-2222-2222-2222-222222222222"),
                    rationale="Human choice",
                    actor="operator:test",
                )


if __name__ == "__main__":
    unittest.main()
