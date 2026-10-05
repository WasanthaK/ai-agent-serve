# Technical Roadmap

## Product direction

The project is evolving into an independent **Expert Agent Platform** shared by the Quixo product family.

### North star

Build continuously learning domain-expert agents that understand real-world service requirements and operating conditions, identify uncertainty and risk, and transform that evidence into safe, predictable, commercially actionable work scopes and proposals.

The Expert Agent Platform owns expertise, reasoning, clarification, contextual intelligence, provenance and controlled learning.

Quixo products retain their own transactional authority:
- **SendQuote** — provider quotation workflow
- **RequestQuote** — public/governed demand and RFQ workflow
- **Marketplace** — sourcing/matching feeding RequestQuote and consuming expert intelligence
- **Connectors/shared services** — widget, email, WhatsApp, voice, Messaging, Identity and other established platform capabilities

Future **Task Scheduler / Workforce / Service Delivery** is a separate product/project, not an agent submodule.

Products and the Expert Agent remain separate so each can evolve, deploy and roll back independently behind versioned contracts.

Canonical target architecture: `docs/AGENT-QUOTES-BOUNDARY.md`.

## Design principles

Every phase should preserve these principles:

- Language models provide interpretation and recommendations.
- Deterministic application code controls authority and state transitions.
- Human approval is required for consequential or high-risk actions.
- Skills are explicit, versioned and testable.
- Tools are registered, state-aware and auditable.
- Canonical business messages remain owned by Quixo Messaging/product connectors; agent persistence is analysis/provenance evidence, not a competing conversation ledger.
- Failures must not lose agent evidence or corrupt the owning product's business events.
- External actions require authentication, authorization and an audit trail.
- The Mac Mini remains a lightweight orchestration node.

## Completed foundation

### Phase 1 — Structured AI intake

- Dockerised FastAPI service
- OpenAI Responses API
- Strict structured analysis
- Health endpoint
- Quote-request classification

### Phase 2 — Durable state

- PostgreSQL persistence
- UUID request tracking
- Stored analysis and workflow status
- Docker Compose health checks
- Installation and troubleshooting documentation

### Phase 3 — Controlled workflows

- Missing-information detection
- Customer follow-up questions
- Persistent conversation history
- Conversational reanalysis
- Human approval and rejection
- Workflow-state enforcement
- Append-only audit events
- Registered, state-aware tool execution
- End-to-end smoke testing

## Phase 4 — Skills, security and operability

### Phase 4A — Skill foundation

Create a reusable skill contract and registry.

Each skill should define:

- Name and version
- Business purpose
- Accepted input schema
- Structured output schema
- Required information
- Risk and escalation policy
- Permitted workflow states
- Permitted tools
- Examples and edge cases
- Evaluation fixtures and tests

Extract the current hardcoded request-analysis behaviour into initial skills:

1. Request intake
2. Request clarification
3. Safety triage
4. Customer communication

### Phase 4B — Authentication and authorization

- Authenticate inbound webhook channels
- Protect operator and administrative endpoints
- Separate customer, operator and system permissions
- Authorize human approval and tool execution
- Prevent secrets from entering logs or events
- Add safe secret rotation procedures
- Preserve private management access

### Phase 4C — Reliability and observability

- Structured application logging
- Correlation IDs across requests, messages and events
- Idempotency keys for webhook delivery
- Retry-safe processing
- Request-size and rate controls
- Operational metrics
- Model-call latency and failure metrics
- Skill-version and tool-version recording
- Health and readiness checks
- Automated unit and integration tests

Phase 4C is complete and live-verified.

Completed proof includes:

- production structured logging and correlation persistence
- webhook idempotency and retry-safe startup recovery
- request-size and authenticated rate controls
- protected operational and model-call metrics
- persisted skill and tool version provenance
- public liveness and database-backed readiness checks
- automated GitHub Actions unit testing
- PostgreSQL 16 fresh-database integration testing
- full migration-chain bootstrap and idempotency verification
- real persistence round-trip validation against a clean database

### Phase 4D — Channel-neutral request inbox

Phase 4D software work is complete.

Completed slices:

- strict `NormalizedInboundMessage` contract with sender and attachment envelope types
- documented trust boundary: adapters authenticate/bind source; normalized payload carries data, not authority
- existing website `POST /webhook/quote-request` internally translated into the normalized contract while preserving its external API, source authentication/mismatch checks, idempotency identity and response shape
- website adapter CI verification completed successfully in PR #21
- channel-bound inbound credentials added and CI-verified in PR #22, while preserving the legacy single-channel deployment path
- provider-neutral `EmailInboundEnvelope` and email normalization contract defined and CI-verified in PR #23 with strict sender/message/thread/timestamp/attachment handling
- durable `inbound_messages` persistence added and CI-verified in PR #24
- exact provider retries are idempotent by `(channel, external_message_id)` and conflicting reuse fails closed
- normalized sender, message/thread identifiers, occurrence timestamp, attachments, correlation ID and optional request linkage are preserved
- inbound-to-request linking is one-way/idempotent and refuses relinking to a different request
- verified SendGrid inbound email ingress implemented and CI-verified in PR #25
- SendGrid ingress verifies provider authenticity before parsing, persists before AI analysis and uses deterministic request identity for retry recovery
- provider-neutral WhatsApp envelope and trusted Quixo Messaging -> Agent ingress implemented and CI-verified in PR #26
- the existing Quixo Azure messaging service remains the public Twilio webhook boundary; the Mac Mini is not exposed directly to Twilio
- WhatsApp forwarding requires a credential explicitly bound to the `whatsapp` channel, persists before AI and uses deterministic request identity for retry recovery
- website normalized inbound persistence before AI, durable request linkage and completed-retry backfill implemented and CI-verified in PR #27
- validated website `Idempotency-Key` values are represented only by SHA-256 hashes in durable inbound-message identity; raw keys are not stored there

External enablement remains deliberately separate from software completion:

- live SendGrid DNS/MX/public webhook enablement remains deferred
- live Twilio/Quixo WhatsApp end-to-end proof remains deferred
- no DNS, MX, public endpoint, Twilio sender/webhook, Azure messaging, firewall, tunnel or port-forwarding changes without explicit authorization immediately before the action

Initial adapters:

- Website webhook — software path complete and CI-verified
- Email — SendGrid software path complete and CI-verified; live external enablement deferred
- WhatsApp — Quixo Messaging -> Agent software path complete and CI-verified; Twilio remains upstream of the existing Quixo messaging service

Later adapters:

- SMS
- Voice transcription
- Marketplaces
- Social channels

Channel adapters should translate messages into the common request format. They must not contain service-delivery reasoning themselves.

## Architecture supersession notice — Phases 5–7

**The implementation history below remains valid evidence of work completed, but its
transactional ownership model is superseded by the product-family architecture in
`docs/AGENT-QUOTES-BOUNDARY.md`.**

Do not extend the local provider directory, RFQ, quote/award, delivery, closure or
messaging modules as new production systems of record. Treat them as prototype,
behavioural, safety and learning evidence until replaced by versioned integration
contracts with the owning Quixo product.

## Phase 5 — Provider routing and quotations

### Phase 5A — Provider management

Phase 5A is complete.

Completed:

- Approved-provider directory foundation implemented and CI-verified in PR #28
- durable provider identity
- explicit approval states: `pending`, `approved`, `suspended`, `rejected`
- repository-level approved-only reads
- provider approval remains application authority, never model authority
- provider service capabilities implemented and CI-verified in PR #29
- service capabilities use only canonical slugs from `agent_skills/service_catalog.py`
- duplicate provider/service assignments are idempotent
- approved-provider service lookup requires both persisted `approved` state and explicit capability assignment
- provider coverage areas implemented and CI-verified in PR #30
- coverage uses explicit canonical lowercase area keys with exact matching only
- duplicate provider/area assignments are idempotent
- approved-provider area eligibility requires persisted approval, exact service capability and exact area assignment
- provider availability indicators implemented and CI-verified in PR #31
- availability uses only `unknown`, `available`, `unavailable`
- missing/unknown availability fails closed
- available-provider eligibility requires approval, service, area and explicit `available` status
- provider compliance status implemented and CI-verified in PR #32
- compliance uses only `unknown`, `compliant`, `non_compliant`
- missing/unknown compliance fails closed
- fully eligible provider filtering requires approval, service, area, availability and compliance
- provider invitation and onboarding implemented and CI-verified in PR #33
- invitation secrets are generated securely and only SHA-256 hashes are persisted
- explicit invitation lifecycle: `pending`, `accepted`, `revoked`, `expired`
- explicit onboarding lifecycle: `not_started`, `in_progress`, `submitted`, `completed`
- onboarding completion never grants provider approval or compliance

Provider management roadmap:

- Approved-provider directory — complete
- Service capabilities — complete
- Coverage areas — complete
- Availability indicators — complete
- Compliance and approval status — complete
- Provider invitation and onboarding — complete

### Phase 5B — Routing skill

Routing starts from deterministic provider eligibility. Explanations may describe proven eligibility evidence but cannot create eligibility, broaden policy, rank providers, or grant provider authority.

Completed:

- deterministic candidate construction implemented and CI-verified in PR #34
- `provider_routing` registered as a built-in skill without changing `DEFAULT_ANALYSIS_SKILLS`
- unranked candidates come only from the fully eligible provider-directory query
- routing preserves exact service and exact area matching
- candidate output exposes only provider ID and display name
- an empty candidate set returns `no_eligible_provider` and requires human review
- PostgreSQL proof verifies persisted compliance is enforced before candidate construction
- deterministic routing explanation implemented and CI-verified in PR #35
- explanations reconstruct candidates internally from persisted eligibility
- explanations are explicitly unranked and unselected
- empty-result explanations do not invent provider-specific failure reasons
- ranking-policy governance implemented and CI-verified in PR #36
- ranking remains disabled by default
- eligibility gates cannot be converted into ranking points
- future ranking factors require deterministic evidence, normalization, missing-data, freshness and weight rules
- provider selection remains human-only and ties require human review

Completed response-reliability foundation:

- historical response-reliability evidence implemented and CI-verified in PR #37
- response opportunities and quote/decline responses are persisted separately
- on-time quotes and on-time declines both count as reliable responses
- late responses and expired no-response opportunities count as completed but not on time
- still-open opportunities are excluded
- the metric uses a rolling 90-day window and requires 5 completed opportunities
- reliability is deterministic integer basis points from 0 to 10,000
- insufficient history remains unscored
- the factor remains inactive until real RFQ handoff generates governed production history

Completed human-selection foundation:

- immutable human-approved provider selection implemented and CI-verified in PR #38
- selection is allowed only from actionable request states: `ready` or `approved`
- selection requires the existing operator `decide` permission
- the deterministic eligible set is rebuilt and locked inside the selection transaction
- selected providers must belong to that current eligible set
- the full eligible-provider snapshot and selected provider set are persisted
- provider selection is a set, never an ordering or ranking
- `provider_selection_recorded` is written in the same transaction
- exact retries are idempotent and conflicting retries fail closed

Completed RFQ handoff foundation:

- durable RFQ snapshot preparation implemented and CI-verified in PR #39
- one stable provider-specific prepared handoff identity is created per selected provider
- RFQ snapshots contain exact service, exact area, request summary and urgency only
- customer name and raw customer message are not copied into the RFQ foundation record
- preparation requires operator `decide`; retrieval requires `read`
- first preparation is allowed only while the request is `ready` or `approved`
- `rfq_handoff_prepared` is written in the same transaction
- exact retries return the original RFQ and original handoff IDs
- preparation creates no response-reliability opportunity

Completed RFQ delivery / response-opportunity activation:

- software-only delivery authorization and confirmation implemented and CI-verified in PR #40
- both transitions require operator `decide`
- current provider eligibility is re-checked before authorization and confirmation
- authorization performs no provider contact
- delivery confirmation requires an explicit timezone-aware response deadline
- response-reliability opportunity creation is atomic with delivery confirmation
- exact retries are idempotent and conflicting deadlines fail closed

Completed provider-response ingestion:

- governed structured provider-response ingestion implemented and CI-verified in PR #41
- only delivered RFQ handoffs accept responses
- only `quote` and `decline` outcomes are accepted
- response timestamps must be timezone-aware and cannot predate delivery
- responses are bound deterministically to the handoff and provider
- ingestion requires operator `decide`
- `rfq_provider_response_recorded` is written transactionally
- exact retries are idempotent and conflicting evidence fails closed
- PostgreSQL response-ingestion integration proof is explicitly included in CI

Completed ranking-readiness guard:

- ranking-readiness assessment implemented and CI-verified in PR #43
- at least two current eligible providers are required
- every current candidate must have sufficient 90-day response history
- one insufficient-history provider blocks ranking for the whole set
- readiness itself never sorts or selects providers

Completed deterministic response-reliability ranking:

- governed response-reliability ranking implemented and CI-verified in PR #44
- ranking executes only when readiness succeeds
- candidates are ordered by deterministic reliability basis points
- equal scores share the same rank position
- ties require human review
- provider selection remains human-only with no automatic selection

Completed normalized quote foundation:

- immutable normalized commercial quote persistence implemented and CI-verified in PR #45
- normalization requires a delivered RFQ handoff and persisted provider `quote` response
- normalized fields include amount, currency, scope, exclusions, terms and optional availability/duration/validity
- writes require operator `decide`; reads require `read`
- exact retries are idempotent and conflicting normalized data fails closed
- no document parsing, model extraction, comparison, recommendation, or award authority was introduced

Completed quote completeness validation:

- deterministic quote completeness implemented and CI-verified in PR #46
- explicit exclusions and terms disclosure are required for comparison readiness
- expired quotes block comparison and require human review
- missing availability, duration and validity are reported as informational gaps
- completeness never evaluates merit, recommends, selects, or awards

Completed deterministic quote comparison:

- factual quote comparison implemented and CI-verified in PR #47
- only comparison-ready normalized quotes from the same request are compared
- mixed currencies are never price-compared and no FX conversion is performed
- price, availability and duration facts are surfaced only when comparable
- scope, exclusions and terms remain side-by-side evidence without scoring
- no overall winner, recommendation, selection or award is produced automatically

Completed human quote recommendation:

- immutable human-authored quote recommendation implemented and CI-verified in PR #48
- recommended quote must belong to the current comparison-ready set
- explicit human rationale is required
- deterministic comparison facts are snapshotted at recommendation time
- writes require operator `decide`; reads require `read`
- recommendation creates no award, provider contact, request-state change or dispatch

Completed human quote award:

- immutable human quote award implemented and CI-verified in PR #49
- award is tied to the existing human recommendation
- quote comparison-readiness and current provider eligibility are re-checked at award time
- writes require operator `decide`; reads require `read`
- exact retries are idempotent and conflicting awards fail closed
- award creates no provider contact, dispatch, or request-state mutation

Completed post-award delivery handoff:

- immutable internal service-delivery handoff implemented and CI-verified in PR #50
- awarded provider, price, currency, scope, exclusions, terms, availability and duration are snapshotted
- request transition to the existing `actioned` state and `actioned_at` is atomic with handoff creation
- writes require operator `decide`; reads require `read`
- exact retries are idempotent and conflicting handoffs fail closed
- handoff creates no provider contact, dispatch, appointment or notification send

Completed delivery notification preparation:

- exactly one customer and one provider notification implemented and CI-verified in PR #51
- message purpose and content are derived deterministically from persisted delivery facts
- destination channel/address remain unresolved rather than inventing outbound authority
- preparation requires operator `decide`; retrieval requires `read`
- repeated preparation is idempotent
- no email, WhatsApp, SMS or other external message is sent

Completed delivery appointment state:

- one human-controlled appointment proposal per actioned request implemented and CI-verified in PR #52
- proposal requires a timezone-aware future window and explicit reason
- explicit human confirmation is required before delivery can be scheduled
- exact proposal and confirmation retries are idempotent; conflicting evidence fails closed
- writes require operator `decide`; reads require `read`
- no external calendar booking or notification send is performed

Completed delivery execution status tracking:

- confirmed appointment -> `scheduled` -> `in_progress` implemented and CI-verified in PR #53
- scheduling and start both require explicit human evidence
- exact retries are idempotent; conflicting evidence fails closed
- writes require operator `decide`; reads require `read`
- no completion, exception, dispatch, calendar, or notification side effects are introduced

Completed delivery exception recording:

- immutable `delay` and `service_issue` evidence implemented and CI-verified in PR #54
- caller-supplied UUIDs provide retry identity
- occurrence and optional expected-resolution timestamps are timezone-aware
- delays are allowed while scheduled/in-progress; service issues require in-progress delivery
- exact retries are idempotent; conflicting UUID reuse fails closed
- writes require operator `decide`; reads require `read`
- no exception resolution, delivery-state mutation, intervention creation, or notification side effect is introduced

Completed human intervention queue:

- one intervention item per recorded exception implemented and CI-verified in PR #55
- priorities are explicit: `normal`, `high`, or `urgent`
- creation and acknowledgement both require explicit human reasons
- exact retries are idempotent; conflicting evidence fails closed
- exception retrieval reflects persisted intervention existence
- writes require operator `decide`; reads require `read`
- no exception resolution, delivery-state mutation, notification send, dispatch, or external action is introduced

Completed service completion confirmation:

- explicit human-controlled `in_progress` -> `completed` transition implemented and CI-verified in PR #56
- completion requires operator `decide` and explicit human reason
- completion is blocked while any linked intervention remains `open`
- acknowledged interventions do not erase historical exception/intervention evidence
- exact retries are idempotent; conflicting completion evidence fails closed
- delivery-status retrieval reports persisted exception history truthfully
- higher-level request status remains `actioned`
- no completion notification or external action is performed

Completed delivery event history:

- deterministic read-only Phase 6 delivery timeline implemented and CI-verified in PR #57
- current `delivery_*` and `human_intervention_*` events are reconstructed in stable order
- original event ID, actor, correlation ID, details, and timestamp are preserved
- known lifecycle stages are labeled while unknown future delivery events remain visible
- summary flags expose completion, exception, and intervention history
- access requires operator `read` only and introduces no write or execution authority

Routing roadmap:

- Deterministic candidate construction — complete
- Routing explanation from deterministic evidence — complete
- Ranking policy design — complete
- Historical response-reliability evidence foundation — complete
- Human-approved provider selection — complete
- RFQ handoff foundation — complete
- RFQ delivery / response-opportunity activation — complete
- Provider-response ingestion — complete
- Ranking-readiness guard — complete
- Deterministic response-reliability ranking — complete

Target routing behavior:

- Match category and service area
- Respect approved-provider policies
- Explain routing decisions
- Escalate when no suitable provider is available

### Quotation workflow

- Create structured requests for quotation — foundation complete
- Collect provider responses — structured response ingestion complete
- Normalize different quotation formats — foundation complete
- Detect missing scope, exclusions and terms — complete
- Compare price, availability, scope and risk — deterministic comparison complete
- Present recommendations for human approval — complete through human award

Purchase-order creation remains outside the initial scope.

## Phase 6 — Service-delivery coordination

Completed:

- Post-award internal delivery handoff and request transition to `actioned` — PR #50
- Durable customer/provider notification preparation with unresolved destinations — PR #51
- Human-controlled appointment proposal and confirmation state management — PR #52
- Delivery execution status tracking: `scheduled` → `in_progress` — PR #53
- Immutable delay and service-issue recording against active delivery — PR #54
- Human intervention queue creation and acknowledgement — PR #55
- Human-controlled service completion confirmation: `in_progress` → `completed` — PR #56
- Complete read-only Phase 6 delivery event history — PR #57

Dependency-independent Phase 6 software work is complete.

Deferred messaging-dependent work:

- Notification destination resolution and delivery authorization

## Phase 7 — Closure and learning

Completed satisfaction follow-up preparation:

- one durable customer satisfaction follow-up after completed delivery implemented and CI-verified in PR #58
- deterministic 1–5 question text is persisted
- destination channel/address remain unresolved
- preparation requires operator `decide`; retrieval requires `read`
- repeated preparation is idempotent
- no follow-up send or external action is performed

Completed satisfaction response ingestion:

- one immutable satisfaction response against the prepared follow-up implemented and CI-verified in PR #59
- integer ratings 1–5 plus optional customer comment are supported
- response timestamps must be timezone-aware, non-future, and not predate follow-up creation
- explicit response evidence source and operator `decide` are required
- exact retries are idempotent; conflicting response evidence fails closed
- no automated review request, complaint, rework, or external action is triggered

Completed public review-request preparation:

- one durable public-review request after satisfaction response implemented and CI-verified in PR #60
- explicit operator reason and operator `decide` are required
- preparation is not satisfaction-rating gated
- review target platform/link remain unresolved
- outbound destination channel/address remain unresolved
- exact retries are idempotent; conflicting evidence fails closed
- no review request is sent and no external action is performed

Completed complaint and rework escalation foundation:

- human-owned closure escalation records implemented and CI-verified in PR #61
- supported kinds are limited to `complaint` and `rework`
- at most one escalation of each kind is allowed per request
- explicit priority, operator reason and operator `decide` are required
- escalation is not inferred automatically from satisfaction rating
- rework escalation does not reopen completed delivery or dispatch work
- exact retries are idempotent; conflicting same-kind evidence fails closed
- no notification or external action is performed

Completed factual outcome measurement:

- read-only factual request outcome projection implemented and CI-verified in PR #62
- persisted delivery completion, satisfaction evidence, review preparation, exception/intervention counts, complaint and rework presence are exposed
- operator `read` is required
- no provider score/rank is computed
- no training signal, policy change, mutation, message, or external action is applied

Completed real-case skill evaluation:

- human-reviewed real-case skill evaluation implemented and CI-verified in PR #63
- evaluations bind to exact persisted analysis-event provenance
- only skill/version pairs proven in that event's `skill_versions` map are eligible
- factual outcome evidence is snapshotted at evaluation time
- verdicts are limited to `pass`, `needs_review`, and `fail`
- exact retries are idempotent; conflicting evidence fails closed
- no training signal, version change, policy change, promotion, or production behavior change is applied

Completed controlled skill improvement proposals:

- human-authored instruction/policy improvement proposals implemented and CI-verified in PR #64
- proposals require `needs_review` or `fail` real-case evaluations
- current registered skill version must still match the evaluated historical version
- current instructions are snapshotted before proposal creation
- scopes are limited to `instructions` and `policy`
- exact retries are idempotent and conflicting evidence fails closed
- no apply endpoint, registry/version mutation, policy activation, or production behavior change exists

Completed regression gate before promotion:

- immutable proposal-linked regression evidence implemented and CI-verified in PR #65
- every suite requires at least one known failing target case and one known-good regression case
- target cases must be baseline failures and regression cases must be baseline passes
- the gate passes only when all target cases are fixed and no candidate case fails
- current registered skill version and instructions must still match the proposal base snapshot
- exact retries are idempotent and conflicting evidence fails closed
- no apply endpoint, registry/version mutation, promotion, or production behavior change exists

Completed training workspace access layer:

- read-only training workspace projection implemented and CI-verified in PR #66
- evaluation, proposal and regression evidence are consolidated into one training case
- deterministic stages expose accepted, proposal-needed, regression-needed, regression-failed and promotion-review-ready cases
- only backend-supported actions are exposed
- access requires operator `read`
- no model-judge, promotion, registry, prompt, policy, or production authority was introduced

Completed failed-regression revision path:

- immutable numbered revisions implemented and CI-verified in PR #67
- each revision links to the exact failed regression result it supersedes
- only the latest candidate may receive new regression evidence
- the original proposal and all prior failed evidence remain immutable
- exact revision retries are idempotent and conflicting revisions fail closed
- the training workspace exposes revision creation only from regression-failed cases
- revised candidates return to regression testing and may become promotion-ready
- no revision applies instructions/policy, mutates the registry, changes skill versions, promotes skills, or changes production behavior

Completed end-user Training / Skill Improvement console:

- operator-facing Training console implemented and CI-verified in PR #68
- real-case context, human evaluation, outcome evidence, proposals, revisions and regression evidence are visible in one workflow
- only backend-authorized actions are exposed
- operator API keys remain in page memory only and are not placed in URLs, cookies or browser storage
- no business data or credentials are embedded in the public HTML shell
- no-store/no-referrer/frame-denial and same-origin content-security controls protect the console boundary

Current bounded work:

- allow controlled human promotion only from passing latest regression evidence
- preserve exact proposal/revision/regression provenance in the promotion record
- deterministically promote the skill to the next minor semantic version
- preserve the existing base instructions and append only the reviewed amendment
- require current runtime version and instructions to exactly match the proposal base snapshot
- activate the promoted version in the live registry only after durable promotion persistence
- restore durable promotions into a fresh registry at runtime startup
- build each analysis call from an atomic current skill-contract snapshot and persist the exact versions used
- expose promotion only to operator `decide`
- show a distinct promoted state in the Training console
- keep promotion human-authorized and regression-gated; model output alone must never activate a change

Phase 7 completion condition:

- controlled promotion passes unit/security/PostgreSQL integration proof and production packaging includes all Phase 7 runtime modules

Planned next after Phase 7:

- Phase 8 — Platform capabilities

Production behaviour must never change solely because of unreviewed model output.

## Phase 8 — Expert platform and Quixo product-family integration

### Phase 8A — Agent access boundary

Completed:

- tenant identity foundation — PR #70
- tenant-bound authentication context — PR #71
- tenant-owned request ingress isolation — PR #72
- downstream request-route isolation — PR #73

These controls protect the agent platform itself. They must not become a second
Quixo business-tenancy model.

The next integration contract must map explicit acting context rather than assuming
one generic tenant id represents provider company, buyer organization and acting
identity.

### Architecture correction — effective immediately

- freeze new authoritative provider/RFQ/quote/award/delivery/messaging domain expansion in `ai-agent-serve`
- retain Phases 5–7 as prototype/reference and behavioural evidence
- keep SendQuote, RequestQuote and Marketplace as independently authoritative products
- keep Marketplace -> RequestQuote as the sourcing/request relationship
- make Marketplace, RequestQuote and SendQuote first-class Expert Agent consumers
- keep existing Messaging authoritative for communication
- support agent invocation both before and after a canonical ServiceRequest/Quotation exists
- use versioned API/event contracts only; no cross-database access or shared ORM entities
- keep future Task Scheduler/Workforce as a separate product/project

### Phase 8B — Requirement Intelligence Package

Define the price-neutral customer/request-side expert contract.

It must represent:

- facts/customer objective
- domain/subdomain
- interpreted scope/work packages
- materials/equipment and labour concepts
- explicitly known quantities
- missing information and clarification questions
- assumptions/exclusions
- safety/compliance
- inspection requirement
- environmental/context constraints
- dependencies
- readiness to request provider pricing
- confidence/evidence provenance

It must distinguish fact, inference, assumption, estimate and unknown and must not
invent provider commercial prices.

### Phase 8C — Commercial Proposal Package

Define the provider-side expert contract consumed by SendQuote/provider workflows.

It may add provider-context work breakdown, commercial structure, duration,
assumptions/exclusions and clearly-labelled pricing suggestions/estimates where
policy permits.

Final prices, taxes, totals, approval and send remain authoritative in SendQuote and
the permitted human/provider workflow.

### Phase 8D — Quixo anti-corruption adapter

Build one explicit `quixo_client` boundary.

Rules:

- versioned HTTP/event contracts
- no direct database access
- no dependency on Quixo table layout
- explicit caller/product surface and acting authority context
- deterministic idempotency/correlation
- bounded retry/timeout behavior
- graceful/manual fallback where appropriate
- contract tests on both sides

Migrate one embedded AI capability at a time using shadow/compare evidence rather
than a big-bang replacement.

### Phase 8E — Canonical reference/provenance linking

Agent evidence may reference authoritative Quixo identifiers without owning their
state.

Examples include ServiceRequest, Quotation and other owning-product identifiers
where applicable.

### Phase 8F — Outcome feedback into learning

Consume factual corrections and outcomes from the owning product.

Priority evidence:

- provider corrections to scope
- clarification deltas
- quote revisions
- acceptance/award outcome
- execution/outcome evidence where a product exposes it
- customer/provider feedback where permitted

No outcome automatically promotes a skill.

### Phase 8G — Context intelligence

Add pluggable external context providers selected by domain skill.

Examples:

- severe weather
- rain/wind/gusts
- temperature/humidity
- UV/heat
- flood/fire
- tides/daylight
- traffic/access
- air quality
- seasonal conditions
- future site sensors

Context changes recommendations/risk evidence only. Deterministic policy decides
whether it is informational, clarification-required, review-required,
rescheduling-recommended or safety-escalated.

Initial proof: one outdoor-work expert skill using weather/environmental context.

### Remaining platform capabilities

- domain/tenant-specific skill overlays
- role-based expert access
- usage accounting
- regional retention/privacy controls
- public integration API
- MCP integration
- private deployment
- optional local GPU inference

## Target expert capability catalogue

| Capability | Expert Agent responsibility |
|---|---|
| Requirement understanding | Interpret messy customer/provider intent and domain context |
| Domain expert scoping | Build professional, domain-specific work scope and work packages |
| Clarification intelligence | Ask the smallest/highest-value questions needed to reduce uncertainty |
| Safety & compliance intelligence | Detect hazards, constraints and review/escalation needs |
| Inspection intelligence | Decide when remote understanding is insufficient for reliable commercialisation |
| Context intelligence | Interpret weather/environment/site factors relevant to the domain |
| Commercial readiness | Assess whether evidence is sufficient to request pricing or prepare a provider proposal |
| Proposal structuring | Produce provider-reviewable commercial structure without taking transactional authority |
| Quote intelligence | Explain/compare factual proposal evidence without selecting or awarding |
| Outcome learning | Learn from human/provider corrections and factual downstream outcomes |

## Definition of done for every capability

A phase or skill is complete only when:

- Inputs and outputs are documented.
- Permitted states and transitions are explicit.
- Human-approval boundaries are defined.
- Success and failure events are recorded.
- Automated tests cover the primary path and invalid transitions.
- Secrets and personal data are handled safely.
- Documentation matches the running implementation.
- The capability passes an end-to-end verification.
