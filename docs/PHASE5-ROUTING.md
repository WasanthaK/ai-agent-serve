# Phase 5B provider routing

## Purpose

Phase 5B converts deterministic provider eligibility into an explicit, unranked candidate set and explains that set using only the eligibility facts already proven by application code.

Routing does not grant authority and does not change provider state. It consumes only persisted provider facts enforced by the Phase 5A provider-management foundation.

## Eligibility boundary

`provider_routing.build_provider_candidates(service_slug, area_key)` delegates eligibility to `provider_directory.list_eligible_providers_for_service_and_area(...)`.

A provider can appear in the candidate set only when all of these persisted facts are true:

1. provider approval status is `approved`;
2. the provider has the requested canonical service capability;
3. the provider has the exact requested coverage-area key;
4. availability status is `available`; and
5. compliance status is `compliant`.

The routing layer does not infer any of those facts and does not broaden coverage when no exact match exists.

## Candidate contract

A non-empty candidate result has:

- `status = eligible_candidates`
- the canonical `service_slug`
- the exact `area_key`
- the fixed eligibility basis
- an ordered list of candidate provider IDs and display names
- `candidate_count`
- `requires_human_review = false`

The order is the stable order returned by the provider directory. It is not a score or ranking.

An empty result has:

- `status = no_eligible_provider`
- an empty candidate list
- `candidate_count = 0`
- `requires_human_review = true`

The application must not silently expand geography, relax compliance, treat unknown availability as available, or invent a provider when the candidate set is empty.

## Deterministic explanation contract

`provider_routing.explain_provider_candidates(service_slug, area_key)` constructs the candidate set internally. It does not accept a caller-supplied or model-supplied provider list.

For each eligible candidate it explains only the five facts already guaranteed by candidate construction:

- persisted approval is `approved`;
- exact requested service capability is present;
- exact requested coverage-area key is present;
- persisted availability is `available`; and
- persisted compliance is `compliant`.

Explanation output explicitly states:

- `ranked = false`; and
- `selected_provider_id = null`.

The explanation layer therefore cannot convert explanation into ranking or selection.

When no provider qualifies, the explanation is deliberately generic: no provider satisfied all required eligibility conditions for the exact service and area. It does not guess which provider failed which eligibility check because ineligible-provider evidence is not part of this contract.

## Skill boundary

`provider_routing` is registered as a built-in skill, version `1.0.0`.

It is intentionally separate from `DEFAULT_ANALYSIS_SKILLS`, so existing request-intake analysis and its JSON schema remain unchanged.

The skill must never invent, add, remove, rank, select, approve, suspend, or contact providers.

This stage exposes no provider-routing HTTP endpoint and registers no write-capable routing tool.

## Current exclusions

This routing stage does not yet include:

- provider ranking or scoring
- automatic provider selection
- RFQ delivery
- provider contact
- fuzzy or proximity geography matching
- availability windows or capacity scoring
- model-controlled provider eligibility
- provider-state mutation

## Verification

Unit tests prove:

- `provider_routing` is registered without changing the existing default intake-analysis skill set;
- candidates are built only from the deterministic eligible-provider query;
- provider fields outside the routing contract are not exposed;
- an empty eligible set always escalates for human review;
- routing explanations use only deterministic candidate evidence;
- explanation output is explicitly unranked and unselected; and
- empty-result explanations do not invent failure reasons or broaden policy.

The PostgreSQL integration proof creates two otherwise matching providers, verifies that a non-compliant provider is excluded, and verifies that the surviving provider receives only the five deterministic eligibility explanations.
