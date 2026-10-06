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

## Channel interaction model

Channels share expert reasoning but intentionally use different interaction policies.

| Channel | Primary interaction | Automatic clarification posture | Canonical outcome |
|---|---|---|---|
| Email | asynchronous, mostly inbound | optional bounded clarification after tenant/product opt-in | same requirement refined until pricing-ready or human review |
| Web widget | synchronous guided conversation | interactive inside the active widget session | customer confirms structured requirement before submit |
| WhatsApp | asynchronous conversational | first-class bounded interaction through Quixo Messaging | multiple turns remain bound to the same requirement |
| Marketplace | interactive product UX | in-product interaction; external communication still product-authorized | refined RequestQuote demand and provider proposal context |
| Future Messenger/social | conversational adapter | policy-controlled | same Requirement Conversation Turn contract |

### Email

Email should remain predominantly an intake channel, not become a chat UI.

Target behavior:

1. ingest and persist the inbound lead/thread in Quixo;
2. ask the Expert Agent for a Requirement Intelligence Package;
3. if sufficient, continue the normal RequestQuote/SendQuote flow;
4. if materially incomplete, generate one concise batch of the highest-value clarification questions;
5. if tenant/product policy explicitly enables automatic clarification, Quixo sends the draft through Messaging in the same email thread;
6. replies continue the **same** requirement and are re-analysed;
7. repeated uncertainty, safety/compliance concerns or policy limits route to human review.

Automatic email clarification never sends a price, promises timing/availability, commits scope, accepts terms or issues a quotation.

Email thread metadata such as provider message id, reply/reference identifiers and normalized conversation identity must survive the connector contract.

### Web widget

The widget is the preferred synchronous requirement-building surface.

The Expert Agent should:

- ask focused questions progressively rather than present a long form
- continuously refine the Requirement Intelligence Package
- show a concise structured summary back to the customer
- make assumptions/unknowns visible
- let the customer correct the interpretation
- reach `ready_for_pricing`, `inspection_required`, `needs_human_review` or `safety_escalation`
- let the owning Quixo product perform the actual request submission

The agent does not create a second widget conversation store.

### WhatsApp

WhatsApp is a primary interactive asynchronous channel.

```text
WhatsApp/Meta
 -> Quixo connector/Messaging
 -> normalize + bind thread/customer/company
 -> Expert Agent requirement turn
 -> Requirement Intelligence Package + reply draft/directive
 -> Quixo policy authorizes delivery
 -> Quixo Messaging sends
 -> customer reply returns to the same thread/request
```

Quixo Messaging remains authoritative for customer-service-window/template behavior.

Text is the first production slice. Voice notes, images and documents are enriched through transcription/vision/document-processing adapters before expert reasoning; a media identifier by itself is never customer requirement text.

### Marketplace

Marketplace uses the Expert Agent on both sides of the sourcing flow.

**Demand side:** interactively help the customer describe the job well enough for RequestQuote to source accurately.

**Provider side:** help the provider understand the request, identify risk/unknowns and prepare a provider-reviewable proposal structure.

Marketplace still feeds RequestQuote for the canonical sourcing/request flow. Expert assistance does not grant Marketplace or the agent quote-send, acceptance or award authority.

### Future conversational channels

Messenger and similar channels should be thin adapters over the same normalized Requirement Conversation Turn contract. They add provider authentication/normalization and delivery behavior, not duplicate expert reasoning.

## Requirement Conversation Turn contract

Minimum request fields:

- schema version
- caller/product surface
- channel
- external message id
- external thread/conversation id where available
- correlation/idempotency reference
- participant role
- provider company / buyer organization / public context as applicable
- optional canonical ServiceRequest/Quotation references
- normalized text
- bounded media/transcript/document references
- previous expert package/reference for continuation
- locale/timezone/context hints when authoritative

Minimum response fields:

- Requirement Intelligence Package
- interaction directive
- clarification questions
- optional channel-neutral reply draft
- confidence/readiness
- safety/human-review flags
- model/skill/provenance identifiers

The reply draft is content only. The owning Quixo product decides if, where and how it is delivered.

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

### A1 — Product-family + messaging contract inventory

Complete the current architecture/contract audit and lock the first interfaces.

- inventory existing SendQuote/RequestQuote/Marketplace AI entry points
- inventory Messaging send/status/WhatsApp-window capabilities
- inventory connector thread/idempotency data
- define explicit acting-context/identifier mapping
- classify agent modules keep/adapt/freeze
- define exact new endpoint ownership before implementation

### A2 — Requirement Conversation Turn + Requirement Intelligence Package v1

Implement the Expert Agent's channel-neutral conversational contract.

No Quixo mutation and no outbound send in this slice.

### A3 — Quixo conversation binding / expert context contracts

Add the minimum Quixo APIs/contracts needed to:

- continue the same requirement across inbound replies
- project authorised request/context data to the Expert Agent
- attach expert evidence/readiness back to the request
- expose pre-quote direct/public request conversation where required

### A4 — Web widget conversational proof

Use the existing widget as the first synchronous production-style proof:

- progressive expert clarification
- structured summary
- customer correction/confirmation
- final RequestQuote submission through existing Quixo authority

### A5 — WhatsApp interactive proof

Use existing Quixo Meta/WhatsApp ingress + Messaging delivery:

- text conversation first
- stable request/thread binding
- expert clarification turns
- bounded automatic replies through Quixo policy
- then voice-note transcription as the next media slice

### A6 — Email asynchronous clarification proof

Keep email mostly inbound.

- expert analyse incoming email
- if incomplete, draft one concise clarification batch
- tenant opt-in required for auto-send
- preserve same email/request thread on reply
- stop at pricing-ready/human-review; never auto-quote

### A7 — Marketplace interactive requirement refinement

Give Marketplace direct expert interaction while preserving Marketplace -> RequestQuote ownership.

### A8 — Commercial Proposal Package v1 / SendQuote delegation

Move provider-side requirement-to-quote intelligence behind the shared expert contract using shadow/compare migration from the existing embedded AI.

### A9 — Outcome feedback and controlled learning integration

Feed provider corrections and factual downstream product outcomes into the existing regression-gated skill learning loop.

### A10 — Context intelligence

First proof: an outdoor-work skill using weather/environmental evidence. Recommendation-only until deterministic product policies are defined.

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
