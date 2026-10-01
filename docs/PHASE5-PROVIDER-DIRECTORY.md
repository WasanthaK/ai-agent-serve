# Phase 5 provider directory foundation

## Purpose

The Phase 5 provider-management foundation is a deterministic source of provider identity, approval state, explicit service capabilities, explicit coverage areas, explicit availability indicators, explicit compliance status, and explicit invitation/onboarding state.

These are eligibility and lifecycle facts only. This stage does not rank, select or route providers and does not yet implement RFQs, quote collection or quote evaluation.

## Authority boundary

Provider approval is application state, not model output.

A language model may later recommend providers or explain why a provider appears suitable, but it must never create, approve, suspend, reject or otherwise mutate provider authority by itself.

The persistence layer accepts only these explicit approval states:

- `pending`
- `approved`
- `suspended`
- `rejected`

Only records whose persisted state is exactly `approved` are returned by approved-provider queries.

Service capability, coverage-area assignment, availability, compliance, invitation and onboarding state are deterministic persisted facts. None is a routing score, endorsement, ranking or provider-selection decision.

Completing onboarding does not grant approval, compliance, availability or routing eligibility.

This stage intentionally exposes no provider-management HTTP mutation endpoint. Authorization and audited lifecycle transitions must remain in the application layer before these persistence primitives are exposed externally.

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

Compliance is application-owned state. This slice does not inspect licenses, insurance documents, expiry dates, certificates or model-generated evidence.

The fully eligible provider query requires all five persisted facts:

1. provider `approval_status = 'approved'`;
2. requested canonical service capability;
3. exact requested coverage-area key;
4. `availability_status = 'available'`; and
5. `compliance_status = 'compliant'`.

The result is an eligible set only. It does not rank, select or route a provider.

## Invitation and onboarding

`provider_invitations` stores invitation metadata and a SHA-256 hash of the one-time invitation secret. The raw invitation secret is returned only at creation time and is never persisted.

Invitation states are explicit:

- `pending`
- `accepted`
- `revoked`
- `expired`

Only one pending invitation is permitted per provider. Expired invitations are durably marked expired so a replacement invite can be created. Repeating acceptance with an already accepted secret is idempotent.

`provider_onboarding` stores one onboarding state per provider:

- `not_started`
- `in_progress`
- `submitted`
- `completed`

Onboarding advances one step at a time. Accepting an invitation moves `not_started` to `in_progress`; later transitions are `in_progress -> submitted -> completed`.

Onboarding completion does not alter provider approval or compliance status.

No email, SMS, WhatsApp or other invitation delivery is performed in this slice. No public acceptance endpoint is exposed.

## Persistence contract

`provider_directory.py` provides provider identity, approval, capability, coverage, availability and compliance persistence/read functions.

`provider_onboarding.py` provides invitation and onboarding lifecycle functions including:

- `create_provider_invitation(...)`
- `accept_provider_invitation(...)`
- `revoke_provider_invitation(...)`
- `get_provider_onboarding(...)`
- `advance_provider_onboarding(...)`

Input validation happens before database access where applicable.

## Current exclusions

This foundation does not yet include:

- compliance evidence documents or expiry handling
- audited provider approval transition APIs
- provider-management HTTP mutation APIs
- invitation delivery through email, SMS, WhatsApp or another external channel
- public invitation-acceptance endpoints
- calendar/time-window availability
- capacity or workload scoring
- proximity/fuzzy/hierarchical area matching
- provider ranking or selection
- RFQ delivery
- quotation ingestion or evaluation

Those remain later Phase 5 or subsequent slices.

## Verification

The PostgreSQL integration suites prove provider identity and approval-state persistence, canonical service capabilities, exact coverage-area assignment, explicit availability, explicit compliance, fail-closed eligibility filtering, hashed invitation-secret persistence, retry-safe invitation acceptance, durable expiry, onboarding lifecycle transitions, and preservation of provider approval/compliance boundaries through onboarding completion.

The migrations are also exercised by the existing fresh-database bootstrap and migration-idempotency checks.
