# Technical Roadmap

## Product direction

The project is evolving into a controlled agent platform for service-delivery request management.

The platform should help service organisations capture requests from multiple channels, collect missing information, identify risk, route work, prepare and evaluate quotations, coordinate delivery and preserve a complete operational history.

This repository contains the open technical implementation and developer documentation. Commercial strategy and pricing are intentionally maintained outside the public repository.

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

### Phase 4D — Channel-neutral request inbox

Create a normalized inbound-message contract so all channels enter the same workflow.

Initial adapters:

- Website webhook
- Email
- WhatsApp

Later adapters:

- SMS
- Voice transcription
- Marketplaces
- Social channels

Channel adapters should translate messages into the common request format. They must not contain service-delivery reasoning themselves.

## Phase 5 — Provider routing and quotations

### Provider management

- Approved-provider directory
- Service capabilities
- Coverage areas
- Availability indicators
- Compliance and approval status
- Provider invitation and onboarding

### Routing skill

- Match category and service area
- Respect approved-provider policies
- Explain routing decisions
- Escalate when no suitable provider is available

### Quotation workflow

- Create structured requests for quotation
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
| Provider routing | Select suitable approved providers | Provider directory |
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
