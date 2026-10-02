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

Current bounded work:

- add software-only RFQ delivery authorization and confirmation state
- require operator `decide` for both transitions
- re-check current provider eligibility before authorization
- move provider handoff from `prepared` to `authorized` without provider contact
- require explicit timezone-aware response deadline for confirmation
- re-check provider eligibility again at confirmation
- move handoff from `authorized` to `delivered`
- atomically create the response-reliability opportunity using handoff ID as opportunity ID
- write `rfq_delivery_authorized` and `rfq_delivery_confirmed`
- make exact retries idempotent and conflicting deadlines fail closed
- do not perform live email/WhatsApp/SMS delivery, ingest provider responses, dispatch work, or activate ranking in this slice

Routing roadmap:

- Deterministic candidate construction — complete
- Routing explanation from deterministic evidence — complete
- Ranking policy design — complete
- Historical response-reliability evidence foundation — complete
- Human-approved provider selection — complete
- RFQ handoff foundation — complete
- RFQ delivery / response-opportunity activation — in progress
- Provider-response ingestion
- Deterministic ranking/reordering — only after real governed RFQ response history exists

Target routing behavior:

- Match category and service area
- Respect approved-provider policies
- Explain routing decisions
- Escalate when no suitable provider is available

### Quotation workflow

- Create structured requests for quotation — foundation in progress
- Collect provider responses
- Normalize different quotation formats
- Detect missing scope, exclusions and terms
- Compare price, availability, scope and risk
- Present recommendations for human approval

Purchase-order creation remains outside the initial scope.

## Phase 6 — Service-delivery coordination

- Appointment proposals and confirmation
- Customer and provider notifications
- Status tracking
- Delay and exception handling
- Human intervention queues
- Service completion confirmation
- Complete event history

## Phase 7 — Closure and learning

- Customer satisfaction follow-up
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
