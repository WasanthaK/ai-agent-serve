# Phase 5 provider directory foundation

## Purpose

The Phase 5 provider directory is a deterministic source of provider identity, approval state, explicit service capabilities, explicit coverage areas, explicit availability indicators and explicit compliance status.

These are eligibility facts only. This stage does not rank, select or route providers and does not yet implement provider onboarding, RFQs, quote collection or quote evaluation.

## Authority boundary

Provider approval is application state, not model output.

A language model may later recommend providers or explain why a provider appears suitable, but it must never create, approve, suspend, reject or otherwise mutate provider authority by itself.

The persistence layer accepts only these explicit approval states:

- `pending`
- `approved`
- `suspended`
- `rejected`

Only records whose persisted state is exactly `approved` are returned by approved-provider queries.

Service capability, coverage-area assignment, availability and compliance are deterministic persisted facts. None is a routing score, endorsement, ranking or provider-selection decision.

This stage intentionally exposes no HTTP provider-management write endpoint. Authorization and audited lifecycle transitions will be added separately before provider-management mutations become available through the application.

## Provider record

`providers` contains:

- `id` — UUID provider identity
- `display_name` — human-readable provider name
- `approval_status` — deterministic approval lifecycle state
- `created_at`
- `updated_at`

Display names are trimmed, must not be blank, and are limited to 200 characters.

## Service capabilities

`provider_service_capabilities` associates a provider with one or more canonical service slugs.

Capability slugs must exist in `agent_skills/service_catalog.py`; the provider directory does not maintain a parallel service taxonomy.

Duplicate provider/service assignments are idempotent.

An approved-provider lookup for a service requires both persisted `approved` state and an explicit matching service capability.

## Coverage areas

`provider_coverage_areas` associates a provider with one or more canonical `area_key` values.

Area keys are stable lowercase identifiers supplied by deterministic application configuration. Examples include `bn:brunei-muara`, `au:nsw:sydney`, `postcode:2000`, and `zone:north-1`.

The provider directory treats an area key as opaque. It does not geocode addresses, infer administrative hierarchy, expand nearby areas, calculate distance or rewrite geographic meaning.

Duplicate provider/area assignments are idempotent.

## Availability indicators

`provider_availability` stores one explicit operational status per provider:

- `unknown`
- `available`
- `unavailable`

Missing, `unknown`, or `unavailable` availability fails closed and is excluded from the available-provider set.

Availability is application-owned state. It is not inferred from messages, model output, historical behaviour or an external calendar in this slice.

## Compliance status

`provider_compliance` stores one explicit compliance status per provider:

- `unknown`
- `compliant`
- `non_compliant`

Missing, `unknown`, or `non_compliant` compliance fails closed and is excluded from the fully eligible provider set.

Compliance is application-owned state. This slice does not inspect licenses, insurance documents, expiry dates, certificates or model-generated evidence. Those can be introduced later behind an audited application boundary.

The fully eligible provider query requires all five persisted facts:

1. provider `approval_status = 'approved'`;
2. requested canonical service capability;
3. exact requested coverage-area key;
4. `availability_status = 'available'`; and
5. `compliance_status = 'compliant'`.

The result is an eligible set only. It does not rank, select or route a provider.

## Persistence contract

`provider_directory.py` provides provider identity, approval, capability, coverage, availability and compliance persistence/read functions, including:

- `set_provider_compliance(...)`
- `get_provider_compliance(...)`
- `list_eligible_providers_for_service_and_area(...)`

Input validation happens before database access.

## Current exclusions

This foundation does not yet include:

- compliance evidence documents or expiry handling
- approval transition APIs
- provider-management HTTP mutation APIs
- provider invitation or onboarding
- calendar/time-window availability
- capacity or workload scoring
- proximity/fuzzy/hierarchical area matching
- provider ranking or selection
- RFQ delivery
- quotation ingestion or evaluation

Those remain later Phase 5 slices.

## Verification

The PostgreSQL integration suite proves provider identity and approval-state persistence, canonical service capabilities, exact coverage-area assignment, explicit availability, explicit compliance, and fail-closed eligibility filtering across all persisted facts.

The migrations are also exercised by the existing fresh-database bootstrap and migration-idempotency checks.
