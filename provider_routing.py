"""Deterministic provider routing for Phase 5B.

This module constructs and explains provider candidate sets from persisted eligibility
facts. It does not rank, select, contact, approve, or otherwise mutate providers.
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


def _eligibility_reasons(service_slug: str, area_key: str):
    """Return fixed explanations for the deterministic eligibility checks."""

    return [
        {
            "code": "approved",
            "detail": "Persisted provider approval status is approved.",
        },
        {
            "code": "service_capability",
            "detail": f"Provider has the exact service capability '{service_slug}'.",
        },
        {
            "code": "exact_coverage_area",
            "detail": f"Provider covers the exact area key '{area_key}'.",
        },
        {
            "code": "available",
            "detail": "Persisted provider availability status is available.",
        },
        {
            "code": "compliant",
            "detail": "Persisted provider compliance status is compliant.",
        },
    ]


def explain_provider_candidates(service_slug: str, area_key: str):
    """Explain a routing candidate set using deterministic evidence only.

    Candidate construction is performed internally so callers cannot inject model-
    supplied providers. Explanations state only the eligibility facts already proven
    by the candidate builder. They do not rank, score, select, or recommend.
    """

    candidate_result = build_provider_candidates(service_slug, area_key)

    if candidate_result["status"] == "no_eligible_provider":
        return {
            "status": "no_eligible_provider",
            "service_slug": service_slug,
            "area_key": area_key,
            "candidate_count": 0,
            "candidates": [],
            "explanation": {
                "code": "no_provider_met_all_requirements",
                "detail": (
                    "No provider satisfied all required eligibility conditions for "
                    "the exact service and area."
                ),
            },
            "ranked": False,
            "selected_provider_id": None,
            "requires_human_review": True,
        }

    reasons = _eligibility_reasons(service_slug, area_key)
    explained_candidates = [
        {
            "provider_id": candidate["provider_id"],
            "display_name": candidate["display_name"],
            "eligibility_reasons": [dict(reason) for reason in reasons],
        }
        for candidate in candidate_result["candidates"]
    ]

    return {
        "status": "eligible_candidates",
        "service_slug": service_slug,
        "area_key": area_key,
        "candidate_count": len(explained_candidates),
        "candidates": explained_candidates,
        "ranked": False,
        "selected_provider_id": None,
        "requires_human_review": False,
    }
