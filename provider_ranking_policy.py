"""Governed provider-ranking policy contract for Phase 5B.

This module defines what must be true before provider ranking can be enabled.
It intentionally performs no scoring and selects no provider.
"""

from dataclasses import dataclass


ELIGIBILITY_GATES = frozenset({
    "approved",
    "service_capability",
    "exact_coverage_area",
    "available",
    "compliant",
})

ALLOWED_FUTURE_FACTORS = frozenset({
    "confirmed_capacity",
    "confirmed_start_time",
    "distance_km",
    "response_reliability",
    "service_quality",
})

PROHIBITED_FACTORS = frozenset({
    *ELIGIBILITY_GATES,
    "provider_id",
    "provider_created_at",
    "protected_characteristic",
    "model_preference",
    "undisclosed_commercial_priority",
})

ALLOWED_DIRECTIONS = frozenset({"higher_is_better", "lower_is_better"})
HUMAN_SELECTION_MODE = "human_only"
HUMAN_TIE_POLICY = "human_review"


class RankingPolicyValidationError(ValueError):
    """A ranking policy violates the deterministic governance contract."""


@dataclass(frozen=True)
class RankingFactorPolicy:
    name: str
    weight: int
    direction: str
    evidence_source: str
    normalization_rule: str
    missing_data_rule: str
    freshness_rule: str


@dataclass(frozen=True)
class ProviderRankingPolicy:
    version: str
    enabled: bool
    factors: tuple[RankingFactorPolicy, ...]
    selection_mode: str = HUMAN_SELECTION_MODE
    tie_policy: str = HUMAN_TIE_POLICY


RESPONSE_RELIABILITY_FACTOR_POLICY = RankingFactorPolicy(
    name="response_reliability",
    weight=100,
    direction="higher_is_better",
    evidence_source="provider_response_reliability_v1",
    normalization_rule=(
        "reliability_bps=floor(on_time_responses*10000/completed_opportunities)"
    ),
    missing_data_rule=(
        "fewer_than_5_completed_opportunities=insufficient_history_and_not_scored"
    ),
    freshness_rule="rolling_90_day_window_at_evaluation_time",
)


CURRENT_PROVIDER_RANKING_POLICY = ProviderRankingPolicy(
    version="1.1.0",
    enabled=True,
    factors=(RESPONSE_RELIABILITY_FACTOR_POLICY,),
)


def validate_provider_ranking_policy(policy: ProviderRankingPolicy) -> ProviderRankingPolicy:
    """Validate policy structure without computing any provider score."""

    if not isinstance(policy, ProviderRankingPolicy):
        raise RankingPolicyValidationError("Ranking policy must use ProviderRankingPolicy")
    if not policy.version or policy.version != policy.version.strip():
        raise RankingPolicyValidationError("Ranking policy version must be canonical text")
    if policy.selection_mode != HUMAN_SELECTION_MODE:
        raise RankingPolicyValidationError("Provider selection must remain human-only")
    if policy.tie_policy != HUMAN_TIE_POLICY:
        raise RankingPolicyValidationError("Ranking ties must require human review")

    if not policy.enabled:
        if policy.factors:
            raise RankingPolicyValidationError(
                "Disabled ranking policy cannot contain active factors"
            )
        return policy

    if not policy.factors:
        raise RankingPolicyValidationError(
            "Enabled ranking policy requires at least one governed factor"
        )

    names = [factor.name for factor in policy.factors]
    if len(names) != len(set(names)):
        raise RankingPolicyValidationError("Ranking factors must be unique")

    total_weight = 0
    for factor in policy.factors:
        if factor.name in PROHIBITED_FACTORS:
            raise RankingPolicyValidationError(
                f"Prohibited ranking factor: {factor.name}"
            )
        if factor.name not in ALLOWED_FUTURE_FACTORS:
            raise RankingPolicyValidationError(
                f"Unsupported ranking factor: {factor.name}"
            )
        if factor.direction not in ALLOWED_DIRECTIONS:
            raise RankingPolicyValidationError(
                f"Unsupported ranking direction for {factor.name}: {factor.direction}"
            )
        if not isinstance(factor.weight, int) or factor.weight <= 0:
            raise RankingPolicyValidationError(
                f"Ranking factor weight must be a positive integer: {factor.name}"
            )

        required_text = {
            "evidence_source": factor.evidence_source,
            "normalization_rule": factor.normalization_rule,
            "missing_data_rule": factor.missing_data_rule,
            "freshness_rule": factor.freshness_rule,
        }
        for field_name, value in required_text.items():
            if not isinstance(value, str) or not value.strip():
                raise RankingPolicyValidationError(
                    f"{field_name} is required for ranking factor {factor.name}"
                )

        total_weight += factor.weight

    if total_weight != 100:
        raise RankingPolicyValidationError(
            "Enabled ranking factor weights must total 100"
        )

    return policy
