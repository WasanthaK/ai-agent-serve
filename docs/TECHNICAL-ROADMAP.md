# Technical Roadmap

## Product direction

The project is evolving into a controlled agent platform for service-delivery request management.

The platform should help service organisations capture requests from multiple channels, collect missing information, identify risk, route work, prepare and evaluate quotations, coordinate delivery and preserve a complete operational history.


## Design principles

Every phase should preserve these principles:

- Language models provide interpretation and recommendations.
- Deterministic application code controls authority and state transitions.
- Human approval is required for consequential or high-risk actions.
- Skills are explicit, versioned and testable.
- Tools are registered, state-aware and auditable.
- Customer messages are stored before downstream AI processing.
- Failures must not lose business events.
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

Current bounded work:

- ingest one immutable satisfaction response against the prepared follow-up
- require integer rating from 1 to 5
- allow optional customer comment
- require timezone-aware response timestamp that is not in the future and does not predate follow-up creation
- require explicit response evidence source and operator `decide`
- make exact retries idempotent and conflicting response evidence fail closed
- record `customer_satisfaction_response_recorded` transactionally
- do not trigger review requests, complaints, rework, or external actions in this slice

Planned next:

- Review-request workflows
- Complaint and rework escalation
- Outcome measurement
- Skill evaluation against real cases
- Controlled improvement of instructions and policies
- Regression tests before skill promotion

Production behaviour must never change solely because of unreviewed model output.

## Phase 8 — Platform capabilities

- Multi-tenant isolation
- Tenant-specific policies and skills
- Role-based access control
- Usage accounting
- Regional data and retention controls
- Public integration API
- MCP integration
- Private deployment options
- Optional local GPU inference

## Initial skill catalogue

| Skill | Responsibility | Likely tools |
|---|---|---|
| Request intake | Classify intent, category and urgency | Request storage |
| Request clarification | Identify essential missing information | Follow-up preparation |
| Safety triage | Detect hazards and enforce escalation | Human-review queue |
| Customer communication | Produce channel-appropriate messages | Email, WhatsApp, SMS |
| Provider routing | Identify and explain suitable approved provider candidates | Provider directory |
| Quote preparation | Create a normalized RFQ | Quotation service |
| Quote evaluation | Compare provider responses | Evaluation records |
| Delivery coordination | Manage appointments and exceptions | Calendar, messaging |
| Service closure | Confirm outcome and request feedback | Review and survey tools |

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
