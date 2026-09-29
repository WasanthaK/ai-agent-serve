# Phase 5 provider directory foundation

## Purpose

The first Phase 5 capability is a deterministic approved-provider directory.

This slice establishes provider identity and persisted approval state only. It does not yet implement service capabilities, coverage areas, availability, compliance evidence, provider onboarding, routing, RFQs, quote collection, or quote evaluation.

## Authority boundary

Provider approval is application state, not model output.

A language model may later recommend providers or explain why a provider appears suitable, but it must never create, approve, suspend, reject, or otherwise mutate provider authority by itself.

The persistence layer therefore accepts only these explicit approval states:

- `pending`
- `approved`
- `suspended`
- `rejected`

Only records whose persisted state is exactly `approved` are returned by the approved-provider directory query.

This slice intentionally exposes no HTTP provider-management write endpoint. Authorization and audited lifecycle transitions will be added separately before provider-management mutations become available through the application.

## Provider record

`providers` contains:

- `id` — UUID provider identity
- `display_name` — human-readable provider name
- `approval_status` — deterministic approval lifecycle state
- `created_at`
- `updated_at`

Display names are trimmed, must not be blank, and are limited to 200 characters.

## Persistence contract

`provider_directory.py` provides:

- `create_provider(...)`
- `get_provider(...)`
- `list_providers(...)`
- `list_approved_providers()`

Input validation happens before database access.

The module does not perform routing or infer whether a provider is suitable for a customer request.

## Service catalogue relationship

Provider service capabilities will be introduced in a later slice and must reference the existing canonical service slugs from `agent_skills/service_catalog.py` rather than create a second category taxonomy.

Examples include `plumbing`, `electrical`, `hvac`, `cleaning`, `mechanic`, and `catering`.

## Current exclusions

This foundation does not yet include:

- provider capability assignments
- coverage areas
- availability indicators
- compliance records
- approval transition APIs
- invitation or onboarding
- matching or ranking
- RFQ delivery
- quotation ingestion or evaluation

Those remain later Phase 5 slices.

## Verification

The PostgreSQL integration suite creates both an approved and a pending provider, reads the approved provider back, and proves that the approved-directory query includes only the explicitly approved provider.

The migration is also exercised by the existing fresh-database bootstrap and migration-idempotency checks.
