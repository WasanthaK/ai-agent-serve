import unittest

from provider_ranking_policy import (
    CURRENT_PROVIDER_RANKING_POLICY,
    RESPONSE_RELIABILITY_FACTOR_POLICY,
    ProviderRankingPolicy,
    RankingFactorPolicy,
    RankingPolicyValidationError,
    validate_provider_ranking_policy,
)


def factor(name="confirmed_capacity", weight=100):
    return RankingFactorPolicy(
        name=name,
        weight=weight,
        direction="higher_is_better",
        evidence_source="deterministic_provider_record",
        normalization_rule="fixed_versioned_rule",
        missing_data_rule="exclude_factor_for_provider_and_require_review",
        freshness_rule="must_be_current_for_request",
    )


class ProviderRankingPolicyTests(unittest.TestCase):
    def test_current_policy_is_disabled_and_human_only(self):
        validated = validate_provider_ranking_policy(CURRENT_PROVIDER_RANKING_POLICY)

        self.assertFalse(validated.enabled)
        self.assertEqual(validated.factors, ())
        self.assertEqual(validated.selection_mode, "human_only")
        self.assertEqual(validated.tie_policy, "human_review")

    def test_response_reliability_factor_is_governed_but_not_active(self):
        factor_policy = RESPONSE_RELIABILITY_FACTOR_POLICY

        self.assertEqual(factor_policy.name, "response_reliability")
        self.assertEqual(factor_policy.weight, 100)
        self.assertEqual(factor_policy.direction, "higher_is_better")
        self.assertEqual(
            factor_policy.evidence_source,
            "provider_response_reliability_v1",
        )
        self.assertIn("10000", factor_policy.normalization_rule)
        self.assertIn("5", factor_policy.missing_data_rule)
        self.assertIn("90", factor_policy.freshness_rule)
        self.assertEqual(CURRENT_PROVIDER_RANKING_POLICY.factors, ())
        self.assertFalse(CURRENT_PROVIDER_RANKING_POLICY.enabled)

    def test_enabled_policy_requires_governed_factors_totaling_100(self):
        policy = ProviderRankingPolicy(
            version="1.0.0",
            enabled=True,
            factors=(
                factor("confirmed_capacity", 60),
                RankingFactorPolicy(
                    name="distance_km",
                    weight=40,
                    direction="lower_is_better",
                    evidence_source="deterministic_geospatial_service",
                    normalization_rule="fixed_versioned_rule",
                    missing_data_rule="exclude_factor_for_provider_and_require_review",
                    freshness_rule="must_be_current_for_request",
                ),
            ),
        )

        self.assertIs(validate_provider_ranking_policy(policy), policy)

    def test_eligibility_gate_cannot_be_used_as_ranking_factor(self):
        policy = ProviderRankingPolicy(
            version="1.0.0",
            enabled=True,
            factors=(factor("compliant"),),
        )

        with self.assertRaises(RankingPolicyValidationError):
            validate_provider_ranking_policy(policy)

    def test_hidden_or_model_driven_tie_breakers_are_prohibited(self):
        for name in (
            "provider_id",
            "provider_created_at",
            "model_preference",
            "undisclosed_commercial_priority",
        ):
            with self.subTest(name=name):
                policy = ProviderRankingPolicy(
                    version="1.0.0",
                    enabled=True,
                    factors=(factor(name),),
                )
                with self.assertRaises(RankingPolicyValidationError):
                    validate_provider_ranking_policy(policy)

    def test_automatic_selection_is_prohibited(self):
        policy = ProviderRankingPolicy(
            version="1.0.0",
            enabled=False,
            factors=(),
            selection_mode="automatic",
        )

        with self.assertRaises(RankingPolicyValidationError):
            validate_provider_ranking_policy(policy)

    def test_non_human_tie_policy_is_prohibited(self):
        policy = ProviderRankingPolicy(
            version="1.0.0",
            enabled=False,
            factors=(),
            tie_policy="provider_id",
        )

        with self.assertRaises(RankingPolicyValidationError):
            validate_provider_ranking_policy(policy)

    def test_enabled_weights_must_total_100(self):
        policy = ProviderRankingPolicy(
            version="1.0.0",
            enabled=True,
            factors=(factor("confirmed_capacity", 90),),
        )

        with self.assertRaises(RankingPolicyValidationError):
            validate_provider_ranking_policy(policy)

    def test_enabled_factor_requires_complete_governance_metadata(self):
        policy = ProviderRankingPolicy(
            version="1.0.0",
            enabled=True,
            factors=(
                RankingFactorPolicy(
                    name="confirmed_capacity",
                    weight=100,
                    direction="higher_is_better",
                    evidence_source="",
                    normalization_rule="fixed",
                    missing_data_rule="review",
                    freshness_rule="current",
                ),
            ),
        )

        with self.assertRaises(RankingPolicyValidationError):
            validate_provider_ranking_policy(policy)


if __name__ == "__main__":
    unittest.main()
