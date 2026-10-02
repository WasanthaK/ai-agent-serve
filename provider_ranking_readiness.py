"""Deterministic provider-ranking readiness assessment.

This module determines whether the current eligible provider set has enough
governed response-reliability evidence to support a future ranking slice.

It does not rank, reorder, select, recommend, or contact providers.
"""

from datetime import datetime
from uuid import UUID

from provider_routing import build_provider_candidates
from provider_response_reliability import (
    calculate_provider_response_reliability,
)


MIN_CANDIDATES_FOR_RANKING = 2


def assess_response_reliability_ranking_readiness(
    service_slug: str,
    area_key: str,
    *,
    as_of: datetime | None = None,
):
    """Assess evidence sufficiency without producing any provider order."""

    candidates_result = build_provider_candidates(service_slug, area_key)
    candidates = candidates_result["candidates"]

    evidence = []
    insufficient_provider_ids = []

    for candidate in candidates:
        provider_id = UUID(candidate["provider_id"])
        metric = calculate_provider_response_reliability(
            provider_id,
            as_of=as_of,
        )
        evidence_item = {
            "provider_id": candidate["provider_id"],
            "display_name": candidate["display_name"],
            "history_status": metric["status"],
            "completed_opportunities": metric["completed_opportunities"],
            "minimum_completed_opportunities": (
                metric["minimum_completed_opportunities"]
            ),
            "reliability_bps": metric["reliability_bps"],
        }
        evidence.append(evidence_item)

        if metric["status"] != "sufficient_history":
            insufficient_provider_ids.append(candidate["provider_id"])

    if len(candidates) < MIN_CANDIDATES_FOR_RANKING:
        readiness_status = "insufficient_candidates"
        readiness_reason = (
            "At least two currently eligible providers are required before "
            "ranking is meaningful."
        )
        ready = False
    elif insufficient_provider_ids:
        readiness_status = "insufficient_history"
        readiness_reason = (
            "Every currently eligible provider must have sufficient governed "
            "response history before reliability-based ranking can be enabled."
        )
        ready = False
    else:
        readiness_status = "ready_for_ranking_implementation"
        readiness_reason = (
            "All currently eligible providers have sufficient governed response "
            "history for the configured reliability factor."
        )
        ready = True

    return {
        "status": readiness_status,
        "service_slug": service_slug,
        "area_key": area_key,
        "candidate_count": len(candidates),
        "minimum_candidates_for_ranking": MIN_CANDIDATES_FOR_RANKING,
        "evidence": evidence,
        "insufficient_history_provider_ids": insufficient_provider_ids,
        "ranking_implementation_ready": ready,
        "ranking_policy_enabled": False,
        "ranked": False,
        "selected_provider_id": None,
        "readiness_reason": readiness_reason,
    }
