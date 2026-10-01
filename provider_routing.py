"""Deterministic provider-routing candidate construction for Phase 5B.

This module filters through persisted provider eligibility facts. It does not rank,
select, contact, approve, or otherwise mutate providers.
"""

from provider_directory import list_eligible_providers_for_service_and_area


ELIGIBILITY_BASIS = (
    "approved",
    "service_capability",
    "exact_coverage_area",
    "available",
    "compliant",
)


def build_provider_candidates(service_slug: str, area_key: str):
    """Build an unranked provider candidate set from deterministic eligibility.

    Service and area validation is delegated to the provider directory, which also
    fails closed on approval, availability, and compliance requirements.
    """

    providers = list_eligible_providers_for_service_and_area(
        service_slug,
        area_key,
    )

    candidates = [
        {
            "provider_id": str(provider["id"]),
            "display_name": provider["display_name"],
        }
        for provider in providers
    ]

    if not candidates:
        return {
            "status": "no_eligible_provider",
            "service_slug": service_slug,
            "area_key": area_key,
            "eligibility_basis": list(ELIGIBILITY_BASIS),
            "candidates": [],
            "candidate_count": 0,
            "requires_human_review": True,
        }

    return {
        "status": "eligible_candidates",
        "service_slug": service_slug,
        "area_key": area_key,
        "eligibility_basis": list(ELIGIBILITY_BASIS),
        "candidates": candidates,
        "candidate_count": len(candidates),
        "requires_human_review": False,
    }
