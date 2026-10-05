# Expert Agent Platform ↔ Quixo Product Family Architecture

> Canonical target architecture for `ai-agent-serve`.
>
> This document describes the intended product-family boundary after reconciling the
> agent roadmap with the current Quixo `quotes/dev` canonical documents. Existing
> runtime paths in this repository may still reflect earlier prototype ownership;
> those paths are preserved until deliberately migrated.

## North star

Build continuously learning domain-expert agents that understand messy real-world
service requirements, operating context, uncertainty and risk, and turn that
evidence into commercially actionable work scopes and proposals.

The Expert Agent Platform is a shared intelligence capability. It is **not** a new
transactional product, a replacement for SendQuote/RequestQuote/Marketplace, or a
mandatory gateway through which every Quixo request must pass.

## Quixo product family

The current product family should be understood as distinct products/capabilities
that collaborate through explicit contracts.

### SendQuote

Provider-facing quotation product.

Owns the provider's transactional quote workflow, including provider review,
commercial values, server-authoritative totals, quote revision/approval and send
authority.

SendQuote already contains basic AI capabilities. Those capabilities should be
progressively delegated to the Expert Agent Platform where the expert service adds
value; they do not need to be removed in one migration.

### RequestQuote

Demand/customer/buyer-side product.

Owns public and governed request/RFQ journeys, request identity, buyer context,
clarifications, response collection, comparison surfaces and acceptance/award
authority according to the existing product rules.

### Marketplace

Sourcing/matching capability.

Marketplace **feeds RequestQuote demand/sourcing flows** and is also a first-class
consumer of the Expert Agent Platform for richer request understanding, domain
classification, matching context, risk/context interpretation and explainable
provider-fit evidence.

Marketplace is not the owner of the expert reasoning engine and the agent is not
the owner of Marketplace transactional state.

### Connectors

Examples:

- web widget
- email parser/intake
- WhatsApp parser/intake
- voice
- webhook/API intake
- future external marketplaces/channels

Connectors deliver demand or provider-side input into the appropriate Quixo
product. They may invoke the Expert Agent **before** a canonical ServiceRequest or
Quotation exists when intelligence is needed during conversational/intake capture.

They should not create a second commercial workflow inside the agent.

### Shared platform services

Existing platform services such as Messaging, Identity, catalogue/category
services, notifications and other shared infrastructure retain their existing
authority.

In particular, **Messaging remains the authoritative communication platform**.
The Expert Agent may consume message content and return drafts/analysis, but it
must not become a second messaging system or canonical conversation ledger.

### Expert Agent Platform

Independent shared intelligence service consumed by SendQuote, RequestQuote,
Marketplace and selected connectors.

It owns:

- requirement interpretation
- domain/subdomain expertise
- expert scoping
- missing-information detection
- clarification strategy
- safety/compliance intelligence
- assumptions and exclusions
- work-breakdown reasoning
- inspection/readiness reasoning
- confidence and uncertainty representation
- environmental/context intelligence
- proposal-structure intelligence
- model/skill provenance
- domain skill packs and versions
- human-reviewed evaluations
- improvement proposals
- regression suites
- controlled skill promotion
- agent-specific telemetry/audit evidence

It does **not** own the authoritative commercial transaction.

### Future Task Scheduler / Workforce / Service Delivery

Task scheduling, workforce/resource management and deeper service-delivery
execution will be developed as a **separate product and project**, not hidden inside
SendQuote, RequestQuote or the Expert Agent Platform.

A future Task Scheduler may own concepts such as:

- jobs/tasks
- technician/staff assignment
- availability/capacity
- shifts
- routing/travel
- skills/certifications
- calendars
- dependencies
- execution evidence
- workforce operations

The Expert Agent may support that future product with expert advice such as job
requirements, technician-skill fit, weather risk or readiness checks, but it will
not own scheduler/workforce state.

## 35,000-foot product topology

```text
              QUIXO PRODUCT FAMILY

       Connectors / Intake Channels
  Web | Widget | Email | WhatsApp | Voice | API
                    |
          +---------+---------+
          |                   |
          v                   v
     RequestQuote         SendQuote
          ^                   ^
          |                   |
      Marketplace             |
          ^                   |
          |                   |
          +---------+---------+
                    |
                    v
          EXPERT AGENT PLATFORM
      shared intelligence / learning

Relationships:
- Marketplace -> RequestQuote for sourcing/request flow.
- Marketplace <-> Expert Agent for matching/request intelligence.
- RequestQuote <-> Expert Agent for requirement intelligence.
- SendQuote <-> Expert Agent for provider/proposal intelligence.
- Connectors may call the Expert Agent during intake and then persist through
  the appropriate Quixo product.
- Future Task Scheduler/Workforce is a separate product that may also consume
  Expert Agent intelligence through versioned contracts.
```

Arrows represent product collaboration, not database ownership.

## Invocation patterns

The Expert Agent must support both patterns.

### 1. Pre-canonical-record intelligence

Useful for voice, widget, email/WhatsApp parsing and conversational capture.

```text
Customer/provider input
  -> connector or Quixo UI
  -> Expert Agent
  -> validated intelligence package
  -> Quixo product creates/updates its canonical record
```

The agent therefore must **not require a ServiceRequest to exist before it can
reason**.

### 2. Post-canonical-record intelligence

Useful for deeper expert analysis of an existing request or quote.

```text
Canonical Quixo record
  -> Expert Agent with stable external reference + allowed context
  -> clarification/scope/risk/proposal intelligence
  -> reviewed result applied through a permitted Quixo API
```

## Two-stage expert outputs

A single universal "commercial requirement" output would conflict with the
existing RequestQuote rule that customer-side intake must not invent provider
pricing. The target architecture therefore uses two related contracts.

### Requirement Intelligence Package

Customer/request-side, price-neutral expert output.

Typical fields:

- schema version
- skill/domain version
- source/correlation reference
- domain/subdomain
- customer objective
- interpreted requirement
- site/job context
- structured scope concepts
- work packages
- materials/equipment concepts
- labour concepts
- quantities explicitly known
- missing information
- clarification questions
- assumptions
- exclusions
- safety/compliance considerations
- inspection requirement
- environmental/context constraints
- dependencies/prerequisites
- readiness to request provider pricing
- confidence by section
- evidence/provenance

It must not fabricate provider prices or turn an estimate into a commercial
commitment.

### Commercial Proposal Package

Provider-side intelligence used when a provider/SendQuote context exists.

May add:

- provider-context work breakdown
- proposed billable structure
- material/labour grouping
- commercial assumptions/exclusions
- duration/timeframe suggestions
- provider-reviewable pricing inputs or estimates **only where policy permits**
- uncertainty around those estimates
- proposal risks
- validity/readiness guidance

Final commercial values, taxes, totals, approval and sending remain authoritative
in SendQuote/Quotes and with the permitted human/provider workflow.

## Evidence semantics

Expert outputs must distinguish:

- supplied fact
- authoritative platform fact
- expert inference
- assumption
- estimate
- unknown/missing information
- safety-critical uncertainty

This distinction must survive adapter translation.

## Context intelligence

Domain skills may declare relevant external context sources, for example:

- severe-weather warnings
- rain
- wind/gusts
- temperature/humidity
- UV/heat
- flood/fire alerts
- tides
- daylight
- traffic/access
- air quality
- seasonal conditions
- future site sensors

Context informs risk and recommendations. It must not silently change commercial
commitments, schedules or workforce assignments.

Deterministic policy decides whether evidence is:

- informational
- clarification-required
- provider-review-required
- rescheduling-recommended
- safety-escalated / stop-work-review-required

## Messaging boundary

Quixo Messaging/product connector infrastructure owns business communication
delivery and the canonical conversation/message record.

The agent may persist only what it needs for:

- model/skill provenance
- analysis reproducibility
- correlation
- evaluation/learning
- bounded retry/recovery

Agent-local message/request rows from the prototype must not become a competing
business conversation source of truth.

## Product/identity context

One generic agent tenant identifier is not enough to represent every Quixo
authority context.

Cross-system calls should carry an explicit acting context such as:

- provider company id, when applicable
- buyer organization id, when applicable
- acting identity user id, when applicable
- public/direct customer reference or token scope, when applicable
- product surface / interaction mode
- canonical ServiceRequest/Quotation reference when one exists

The adapter must not infer one authority from another.

## Independence boundary

The Expert Agent and Quixo products must remain independently evolvable.

Rules:

1. Separate repositories.
2. Separate databases.
3. Separate migrations.
4. Separate deployment and rollback cycles.
5. No shared ORM entities/database schemas.
6. No direct cross-database reads or writes.
7. No dependency on another product's table layout.
8. Integration only through versioned API/event contracts.
9. Stable external identifiers are references, not transferred ownership.
10. Either side may be unavailable without corrupting the other's authoritative state.
11. Agent recommendations mutate product state only through explicitly permitted APIs.
12. Consequential commercial actions remain deterministic/human-controlled per product policy.
13. Contract tests protect both sides from accidental coupling.

This is the safe distance: independent implementation behind stable contracts.

## Existing Quixo AI: migration posture

Quixo already contains useful embedded AI/extraction paths, including
RequestQuote voice/intake, quote extraction, requirement-to-quote assistance and
connector parsing.

Do not perform a big-bang replacement.

Use a strangler/delegation approach:

1. define the expert contract;
2. add an adapter/client in the calling Quixo product;
3. run the Expert Agent in shadow/compare mode where useful;
4. prove parity or improvement;
5. switch one bounded capability;
6. retain a graceful/manual fallback;
7. remove old embedded logic only after evidence and explicit cleanup.

This keeps SendQuote/RequestQuote/Marketplace independently releasable while the
expert engine improves rapidly.

## Existing agent modules

Completed Phase 5-7 commercial-domain work is preserved as historical/prototype,
safety and behavioural evidence. It no longer defines production ownership.

### Keep and deepen

- skill registry
- domain service catalogue
- requirement interpretation
- clarification intelligence
- safety triage
- human review
- provenance
- evaluation/training/regression/promotion
- observability
- agent access/auth boundary
- context intelligence
- Requirement Intelligence Package
- Commercial Proposal Package

### Adapt into integration/projection clients

- request persistence entry paths
- provider lookup/matching evidence
- RFQ/proposal preparation
- quote comparison intelligence
- outcome/evidence retrieval

### Freeze as authoritative production domains

Do not extend as competing systems of record:

- local provider directory/eligibility
- provider invitation/onboarding
- RFQ handoff transaction state
- normalized quote ledger
- quote recommendation/award transaction state
- appointment/delivery execution state
- closure transaction state
- duplicate messaging/channel delivery

Historical tests remain useful behavioural specifications.

## Integration seams already present

Useful current seams in Quixo include, among others:

- `POST /api/v1/quotes/internal/requests`
- `GET /api/v1/providers/internal/search`
- `GET /api/v1/providers/internal/company/{companyId}`

These are starting points, not permission to couple to internal database models.
Additional versioned expert-facing APIs may be required.

## Learning loop

Target loop:

```text
real requirement
 -> expert interpretation
 -> human/provider correction
 -> commercial proposal/quote outcome
 -> service/outcome evidence from the owning product
 -> human evaluation
 -> skill improvement proposal
 -> regression
 -> human-controlled promotion
 -> new skill version
```

No product outcome automatically changes production skill behaviour.

## Contract discipline

Every cross-system contract must define:

- version
- caller/product surface
- authentication
- acting company/buyer/user/public context
- idempotency
- correlation/reference identifiers
- timeout/retry behavior
- error semantics
- privacy/data classification
- authority boundary
- backward compatibility window
- contract tests

## Immediate implementation sequence

### A1 — Product-family contract inventory

- freeze duplicate commercial ownership expansion
- inventory current AI/extraction entry points in SendQuote, RequestQuote,
  Marketplace and connectors
- inventory existing Quixo APIs/events usable by the expert platform
- classify current agent modules as keep/adapt/freeze
- define explicit acting-context/identifier mapping

### A2 — Requirement Intelligence Package v1

Define/test the price-neutral customer/request-side expert contract.

No product mutation.

### A3 — Commercial Proposal Package v1

Define/test the provider-side expert proposal contract with explicit estimate versus
authoritative-price semantics.

No autonomous send/approval.

### A4 — Quixo integration adapter

Create an anti-corruption `quixo_client` boundary rather than product-specific
database coupling.

Initial consumers can be migrated one bounded path at a time.

### A5 — Canonical reference/provenance linking

Persist only stable external references needed for reproducibility and learning.

### A6 — Outcome feedback contract

Consume factual corrections and outcomes from the owning Quixo product.

### A7 — Context intelligence

First proof: one outdoor-work domain skill with weather/environmental evidence,
recommendation-only until deterministic policy thresholds are defined.

## Explicit non-goals

The Expert Agent Platform will not become:

- SendQuote
- RequestQuote
- Marketplace
- a replacement provider database
- a second messaging platform
- a quotation ledger
- a payment/accounting authority
- Task Scheduler/workforce management
- an autonomous commercial decision-maker

Its job is to become the best reusable domain-expert intelligence layer in the
Quixo product family.
