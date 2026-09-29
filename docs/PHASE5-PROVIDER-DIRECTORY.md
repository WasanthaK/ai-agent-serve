# Phase 5 provider directory foundation

## Purpose

The Phase 5 provider directory is a deterministic source of provider identity, approval state, explicit service capabilities and explicit coverage areas.

These are eligibility facts only. This stage does not rank, select or route providers and does not yet implement availability, compliance evidence, provider onboarding, RFQs, quote collection or quote evaluation.

## Authority boundary

Provider approval is application state, not model output.

A language model may later recommend providers or explain why a provider appears suitable, but it must never create, approve, suspend, reject or otherwise mutate provider authority by itself.

The persistence layer accepts only these explicit approval states:

- `pending`
- `approved`
- `suspended`
- `rejected`

Only records whose persisted state is exactly `approved` are returned by approved-provider queries.

Service capability and coverage-area assignment are also deterministic persisted facts. Neither is a routing score, endorsement, ranking or provider-selection decision.

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

Area keys are stable lowercase identifiers supplied by deterministic application configuration. Examples:

- `bn:brunei-muara`
- `au:nsw:sydney`
- `postcode:2000`
- `zone:north-1`

The provider directory treats an area key as opaque. It does not geocode addresses, infer administrative hierarchy, expand nearby areas, calculate distance or rewrite geographic meaning.

Duplicate provider/area assignments are idempotent.

The exact service-and-area eligibility query requires all three persisted facts:

1. provider `approval_status = 'approved'`;
2. the requested canonical service capability; and
3. the exact requested coverage-area key.

The result is an eligible set only. It does not rank or select a provider.

## Persistence contract

`provider_directory.py` provides:

- `create_provider(...)`
- `get_provider(...)`
- `list_providers(...)`
- `list_approved_providers()`
- `add_provider_service_capability(...)`
- `list_provider_service_capabilities(...)`
- `list_approved_providers_for_service(...)`
- `add_provider_coverage_area(...)`
- `list_provider_coverage_areas(...)`
- `list_approved_providers_for_service_and_area(...)`

Input validation happens before database access.

## Current exclusions

This foundation does not yet include:

- availability indicators
- compliance records
- approval transition APIs
- provider-management HTTP mutation APIs
- invitation or onboarding
- proximity/fuzzy/hierarchical area matching
- provider ranking or selection
- RFQ delivery
- quotation ingestion or evaluation

Those remain later Phase 5 slices.

## Verification

The PostgreSQL integration suite proves provider identity and approval-state persistence, canonical service capabilities, exact coverage-area assignment, idempotent duplicate assignments, and approved-provider filtering by exact service plus exact area.

The migrations are also exercised by the existing fresh-database bootstrap and migration-idempotency checks.
