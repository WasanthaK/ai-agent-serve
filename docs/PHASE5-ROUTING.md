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

## Ranking-policy governance

Provider ranking remains disabled by default.

The current provider facts — approval, service capability, exact coverage area, availability and compliance — are eligibility gates. They must not be converted into ranking points because every candidate has already passed them.

`provider_ranking_policy.py` defines the governance contract that must be satisfied before ranking can be enabled.

Any future ranking factor must have all of the following before activation:

- an explicit deterministic evidence source;
- a fixed ranking direction;
- a versioned normalization rule;
- a defined missing-data rule;
- a freshness rule; and
- an integer weight.

When ranking is enabled, active factor weights must total exactly 100.

The policy catalogue currently permits only future operational factors for which deterministic evidence could be added later:

- `confirmed_capacity`
- `confirmed_start_time`
- `distance_km`
- `response_reliability`
- `service_quality`

The first governed factor is now defined as `response_reliability`, but it remains inactive in the current ranking policy. This slice adds the evidence persistence and deterministic metric needed for that factor; production ranking still remains disabled until real RFQ/provider-response history exists and a scoring implementation is separately reviewed.

Explicitly prohibited ranking inputs include:

- any eligibility gate;
- provider ID or provider creation order;
- model preference;
- protected characteristics;
- undisclosed commercial priority.

Provider selection remains `human_only`. Ranking ties require `human_review`; the system must not silently break ties using IDs, creation order or model judgment.

### Historical response reliability evidence

`provider_response_reliability.py` records provider response opportunities and provider responses as separate durable records.

The metric intentionally measures responsiveness rather than willingness to quote:

- an on-time quote counts as an on-time response;
- an on-time decline also counts as an on-time response;
- a late response is completed history but is not on time;
- no response after the deadline is completed history and is not on time;
- an opportunity whose deadline has not passed and has no response is still open and is excluded.

The v1 evidence policy uses:

- a rolling 90-day history window;
- a minimum of 5 completed opportunities;
- an integer reliability scale from 0 to 10,000 basis points;
- `reliability_bps = floor(on_time_responses * 10000 / completed_opportunities)`.

Providers with fewer than five completed opportunities return `insufficient_history` and no reliability score. They are not assigned a low score.

The provider-response opportunity ID is intentionally opaque in this slice. The future RFQ handoff can bind it to the provider-specific RFQ invitation identity without changing the reliability calculation contract.

The current ranking policy remains disabled. This slice computes evidence only; it does not reorder candidates or select a provider.

## Current exclusions

This routing stage does not yet include:

- executable provider ranking/reordering
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

Ranking-policy unit tests additionally prove that ranking is disabled by default, eligibility gates cannot become score factors, automatic selection and arbitrary tie-breaking are rejected, active weights must total 100, and every enabled factor must carry complete governance metadata.

The response-reliability PostgreSQL proof verifies a 90-day history window, exclusion of open opportunities, exclusion of stale history, on-time quote and decline handling, late/no-response handling, deterministic basis-point calculation, idempotent response recording, and fail-closed `insufficient_history` behavior below five completed opportunities.
