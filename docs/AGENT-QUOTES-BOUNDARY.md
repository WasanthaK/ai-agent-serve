# Agent ↔ Quotes Bounded-Context Architecture

## North star

Build domain-expert agents that understand real-world service requirements, account for operating context, identify uncertainty and risk, and transform that evidence into a transaction-ready commercial proposal.

The agent must become exceptionally good at interpretation, scoping, clarification, domain expertise, contextual reasoning and learning.

The Quotes platform remains authoritative for commercial and operational transactions.

## Why this boundary exists

The Quotes repository already contains mature, authoritative implementations for:

- ServiceRequest and governed buyer request ownership
- provider identity, provider lookup and provider service areas
- provider matching and request-provider match records
- RFQ specification/version history
- RequestQuoteMatch and quotation lineage
- quote approval, acceptance and award
- governed buyer/provider clarification
- Engagement/job execution
- scheduling, assignment, start/completion/cancellation
- inspections
- deposit requests
- variations/change orders
- provider permissions and provider-facing UI
- messaging and channel delivery

The agent server must not create a second source of truth for those capabilities.

Completed Phase 5–7 commercial-domain modules in this repository remain useful as prototype, safety, testing and architectural evidence. They are not the future system of record.

## Bounded contexts

### Agent platform owns

The agent platform is authoritative for intelligence and learning:

- requirement interpretation
- intent/domain/subdomain classification
- expert scoping
- missing-information detection
- clarification strategy
- domain-specific safety escalation
- assumptions and exclusions
- work-breakdown reasoning
- commercial-readiness assessment
- confidence and uncertainty representation
- environmental/context intelligence
- proposal drafting assistance
- model/skill provenance
- skill versions and domain skill packs
- human-reviewed real-case evaluations
- improvement proposals
- regression suites
- controlled skill promotion
- agent-specific telemetry and audit evidence

### Quotes owns

Quotes is authoritative for transactional state:

- customers and provider companies
- buyer organisations
- ServiceRequest
- provider directory/profile/service areas
- provider matching
- RFQ lifecycle and immutable request versions
- quotations and RequestQuoteMatch
- approvals/rejections
- acceptance and award
- Engagement/job lifecycle
- inspections
- deposits
- variations/change orders
- commercial messages and customer/provider communication
- billing/payment transaction state
- provider permissions
- transactional UI

## Independence boundary

The two systems must remain independently evolvable.

Rules:

1. Separate repositories.
2. Separate databases.
3. Separate migrations.
4. Separate deployment and rollback cycles.
5. No shared ORM entities or database schemas.
6. No direct database reads/writes across service boundaries.
7. No agent dependency on Quotes internal table layouts.
8. No Quotes dependency on agent persistence layout.
9. Integration only through versioned API/event contracts.
10. Correlation uses stable external identifiers, not shared primary-key ownership.
11. Either side may temporarily be unavailable without corrupting the other's authoritative state.
12. Agent recommendations never mutate Quotes without an explicit permitted API action.
13. Consequential commercial actions continue to require deterministic authority and human approval where policy requires it.

This is an anti-corruption boundary: the agent speaks its own expert proposal contract and a dedicated adapter translates that contract to and from Quotes APIs.

## Canonical flow

```text
Customer / Provider requirement
        |
        v
Existing Quotes Messaging / UI / Connector surfaces
        |
        v
Canonical Quotes ServiceRequest identity
        |
        +------------------------------+
        |                              |
        v                              |
Agent intelligence API                 |
- interpret                            |
- classify domain                      |
- assess context                       |
- ask clarifications                   |
- build scope                          |
- identify risk                        |
- assess pricing readiness             |
- produce Commercial Requirement Package
        |
        v
Human/provider review where required
        |
        v
Quotes integration adapter
        |
        v
Quotes authoritative APIs
- request/RFQ
- quotation
- approval
- award
- Engagement
- downstream execution
        |
        v
Outcome/evidence events
        |
        v
Agent evaluation + controlled learning
```

## Commercial Requirement Package

The core agent output should evolve toward a stable, versioned contract independent of Quotes storage.

Suggested contract areas:

- contract/schema version
- agent skill/domain version
- source request reference
- domain and subdomain
- customer objective
- interpreted requirement
- site/job context
- structured scope of work
- materials/equipment concepts
- labour/work-package concepts
- quantities explicitly known
- explicit assumptions
- explicit exclusions
- missing information
- clarification questions
- safety/compliance considerations
- environmental/context constraints
- dependencies/prerequisites
- pricing-readiness state
- inspection-required state
- commercial risks
- confidence by section
- recommended next action
- evidence/provenance references

The contract must distinguish:

- facts supplied by the customer/system
- expert inference
- assumptions
- estimates
- missing information
- safety-critical uncertainty

## Context intelligence

Domain skills may declare relevant external context sources.

Examples:

- weather and severe-weather warnings
- rainfall probability
- wind/gusts
- temperature/humidity
- UV/heat
- flood/fire warnings
- tides
- daylight
- traffic/access constraints
- air quality
- seasonal conditions
- site sensor data in future

Context data informs recommendations and risk. It must not silently create or change transactional commitments.

A deterministic policy layer decides whether context is:

- informational
- requires provider review
- requires customer clarification
- requires rescheduling recommendation
- requires safety escalation / stop-work review

## Learning loop

Target learning loop:

```text
real requirement
 -> agent interpretation
 -> provider corrections
 -> accepted commercial proposal
 -> service execution
 -> actual outcome
 -> human evaluation
 -> skill improvement proposal
 -> regression suite
 -> human promotion
 -> new skill version
```

Provider corrections are particularly valuable training evidence because they reveal domain-expert deltas between agent interpretation and real commercial practice.

## Integration seams already present in Quotes

The current Quotes codebase already exposes useful boundaries that should be preferred over duplicate persistence:

- `POST /api/v1/quotes/internal/requests`
  - service-to-service connector intake
  - creates canonical ServiceRequest
  - deterministic idempotency
- `GET /api/v1/providers/internal/search`
  - internal provider lookup
- `GET /api/v1/providers/internal/company/{companyId}`
  - authoritative provider lookup

Quotes also already owns ServiceRequest, RequestProviderMatch, ServiceRequestVersion, RequestQuoteMatch, Quotation and Engagement.

Future agent integration should consume or extend versioned Quotes APIs around these authoritative aggregates rather than reproduce them in Python.

## Migration posture for existing agent modules

Do not delete completed work immediately.

Classify modules into three groups.

### Keep and deepen

- skills / skill registry
- domain service catalogue
- request interpretation
- clarification
- safety triage
- human review
- model/skill provenance
- evaluation / training / regression / promotion
- agent observability
- tenant/auth boundary needed for agent access
- contextual intelligence
- Commercial Requirement Package

### Adapt into integration clients

- request persistence entry paths
- provider lookup
- provider matching evidence
- RFQ preparation
- quote normalization/comparison
- delivery/outcome retrieval

These should become clients/projections over Quotes rather than independent authoritative stores.

### Freeze as prototype/reference authority

Until replaced by integration contracts, do not extend:

- local provider directory
- local provider eligibility source of truth
- local provider invitation/onboarding
- local RFQ handoff authority
- local normalized quote authority
- local quote recommendation/award transaction state
- local delivery/appointment execution state
- local closure transaction state

Historical tests remain valuable as behavioural specifications.

## Safe-distance deployment model

The preferred deployment model is not an embedded Python library inside Quotes.

Instead:

```text
Quotes
  <---- versioned HTTPS / event contracts ---->
Agent Service
```

Advantages:

- agent can upgrade models and skills independently
- Quotes can evolve transactional workflows independently
- agent can run locally/private/cloud without forcing Quotes migration
- failures are isolated
- contract tests reveal incompatibility before deployment
- rollback is independent
- multiple agent implementations can eventually target the same Quotes contract
- Quotes can operate in degraded/manual mode if the agent is unavailable

## Contract discipline

Every cross-system contract must define:

- version
- authentication
- tenant/company/buyer context
- idempotency
- correlation identifiers
- timeout/retry policy
- error semantics
- data-classification/privacy rules
- authority boundaries
- backward-compatibility window
- contract tests on both repositories

No integration may rely on undocumented database behavior.

## Immediate implementation sequence

### A1 — Architecture freeze and contract inventory

- mark duplicate commercial-domain expansion frozen
- inventory existing Quotes APIs needed by the agent
- classify each current agent commercial module as keep/adapt/freeze
- document identifier mapping between agent tenant context and Quotes company/buyer context

### A2 — Commercial Requirement Package v1

Define and test the agent's independent proposal contract.

Start with:

- requirement understanding
- domain/subdomain
- scope
- missing information
- clarifications
- assumptions
- exclusions
- safety/compliance
- context/environmental constraints
- pricing readiness
- confidence
- recommended next action

No Quotes mutation in this slice.

### A3 — Quotes integration adapter

Create an explicit `quotes_client` / anti-corruption layer.

Initial read/write seams:

- canonical request lookup/intake
- provider/company lookup only where expert reasoning needs it
- commercial proposal handoff/draft creation through approved Quotes API contracts

No direct database access.

### A4 — Canonical identity linking

Persist only cross-system references needed for provenance:

- agent analysis/evaluation id
- Quotes ServiceRequest id/reference
- Quotes Quotation id where applicable
- Quotes Engagement id where applicable

Quotes remains owner of those identifiers and state.

### A5 — Outcome feedback contract

Read factual outcome evidence from Quotes:

- provider corrections
- quote revisions
- award/acceptance
- service execution outcome
- exceptions
- customer confirmation/satisfaction where permitted

Feed this to the existing controlled learning loop.

### A6 — Context intelligence

Add pluggable context providers and domain policies.

First outdoor-work proof should use weather/environmental evidence but remain recommendation-only until deterministic thresholds and human review rules are defined.

## Explicit non-goals

The agent platform will not become:

- a replacement provider database
- a second RFQ system
- a second quotation ledger
- a second Engagement/job-management system
- a second messaging platform
- a payment/accounting authority
- an autonomous commercial decision-maker

Its job is to become the best domain-expert intelligence layer feeding a robust transactional platform.
