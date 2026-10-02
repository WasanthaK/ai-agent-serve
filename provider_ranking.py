"""Deterministic provider ranking by governed response reliability."""

from provider_ranking_policy import (
    CURRENT_PROVIDER_RANKING_POLICY,
    validate_provider_ranking_policy,
)
from provider_ranking_readiness import (
    assess_response_reliability_ranking_readiness,
)


class ProviderRankingNotReadyError(RuntimeError):
    """The governed evidence set is not ready for deterministic ranking."""


def rank_providers_by_response_reliability(
    service_slug: str,
    area_key: str,
    *,
    as_of=None,
):
    """Rank eligible providers only when governed readiness succeeds."""

    policy = validate_provider_ranking_policy(CURRENT_PROVIDER_RANKING_POLICY)
    if not policy.enabled:
        raise ProviderRankingNotReadyError("Provider ranking policy is disabled")

    readiness = assess_response_reliability_ranking_readiness(
        service_slug,
        area_key,
        as_of=as_of,
    )
    if not readiness["ranking_implementation_ready"]:
        raise ProviderRankingNotReadyError(readiness["readiness_reason"])

    evidence = readiness["evidence"]
    scores = sorted(
        {item["reliability_bps"] for item in evidence},
        reverse=True,
    )
    rank_by_score = {
        score: index + 1
        for index, score in enumerate(scores)
    }
    tied_scores = {
        score
        for score in scores
        if sum(
            item["reliability_bps"] == score
            for item in evidence
        ) > 1
    }

    ranked_candidates = []
    for item in sorted(
        evidence,
        key=lambda candidate: candidate["reliability_bps"],
        reverse=True,
    ):
        score = item["reliability_bps"]
        ranked_candidates.append({
            "provider_id": item["provider_id"],
            "display_name": item["display_name"],
            "rank_position": rank_by_score[score],
            "response_reliability_bps": score,
            "completed_opportunities": item["completed_opportunities"],
            "tied": score in tied_scores,
        })

    return {
        "status": "ranked_candidates",
        "service_slug": service_slug,
        "area_key": area_key,
        "ranking_policy_version": policy.version,
        "ranking_factor": "response_reliability",
        "ranking_direction": "higher_is_better",
        "ranked_candidates": ranked_candidates,
        "candidate_count": len(ranked_candidates),
        "has_ties": bool(tied_scores),
        "requires_human_review": bool(tied_scores),
        "selection_mode": policy.selection_mode,
        "selected_provider_id": None,
        "ranked": True,
    }
