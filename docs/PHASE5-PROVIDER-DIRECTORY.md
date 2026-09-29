# Phase 5 provider directory foundation

## Purpose

The Phase 5 provider directory is a deterministic source of provider identity, approval state and explicit service capabilities.

This stage establishes the minimum persisted facts required before routing can exist. It does not yet implement coverage areas, availability, compliance evidence, provider onboarding, routing, RFQs, quote collection, or quote evaluation.

## Authority boundary

Provider approval is application state, not model output.

A language model may later recommend providers or explain why a provider appears suitable, but it must never create, approve, suspend, reject, or otherwise mutate provider authority by itself.

The persistence layer accepts only these explicit approval states:

- `pending`
- `approved`
- `suspended`
- `rejected`

Only records whose persisted state is exactly `approved` are returned by approved-provider queries.

Service capability assignment is also deterministic persisted state. A capability means only that the provider has been explicitly associated with a canonical service category; it is not a routing score, endorsement or selection decision.

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

Examples include:

- `plumbing`
- `electrical`
- `hvac`
- `cleaning`
- `mechanic`
- `catering`

Duplicate provider/service assignments are idempotent.

An approved-provider lookup for a service requires both:

1. provider `approval_status = 'approved'`; and
2. an explicit matching service capability assignment.

A pending, suspended or rejected provider is not eligible for the approved service directory merely because it has a capability row.

## Persistence contract

`provider_directory.py` provides:

- `create_provider(...)`
- `get_provider(...)`
- `list_providers(...)`
- `list_approved_providers()`
- `add_provider_service_capability(...)`
- `list_provider_service_capabilities(...)`
- `list_approved_providers_for_service(...)`

Input validation happens before database access.

The module does not perform routing, ranking, coverage matching or infer whether a provider is suitable for a specific customer request.

## Current exclusions

This foundation does not yet include:

- coverage areas
- availability indicators
- compliance records
- approval transition APIs
- capability-management APIs
- invitation or onboarding
- matching or ranking
- RFQ delivery
- quotation ingestion or evaluation

Those remain later Phase 5 slices.

## Verification

The PostgreSQL integration suite proves:

- provider identity and approval-state persistence;
- approved-only directory filtering;
- canonical service-capability assignment;
- idempotent duplicate capability assignment; and
- approved-provider lookup by service excludes pending providers and unrelated capabilities.

The migrations are also exercised by the existing fresh-database bootstrap and migration-idempotency checks.
