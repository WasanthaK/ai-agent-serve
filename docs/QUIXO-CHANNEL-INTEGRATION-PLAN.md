# Quixo Channel + Expert Agent Integration Plan

> Planning baseline: Quixo `quotes/dev` + `ai-agent-serve` PR #74 architecture branch.
>
> Goal: reuse the mature Quixo connector/Messaging platform while moving requirement
> interpretation and clarification intelligence into the independent Expert Agent Platform.

## 1. Existing capabilities we should reuse

### Quixo Messaging

Already provides:

- email send through `POST /api/v1/messaging/messages/email/single`
- generic internal send through `POST /api/v1/messaging/messages`
- delivery/status lookup by UMID
- QuoteService `IMessagingClient`
- email, SMS and app notification paths
- WhatsApp template sends
- WhatsApp interactive/text sends
- WhatsApp window-aware send behavior
- quote/request notification helpers

Conclusion: **no SendGrid/Twilio/Meta delivery client should be rebuilt in the Expert Agent.**

### Quixo connector intake

Already provides:

- tenant/provider resolution
- email and WhatsApp inbound webhook boundaries
- inbound idempotency
- RequestDraft normalization
- direct-company routing
- canonical direct connector intake to QuoteService via
  `POST /api/v1/quotes/internal/requests`

### Existing conversation/clarification surfaces

Already provides:

- quote-linked provider/customer conversations
- public quote conversation via quote access token
- governed buyer request clarification threads

Gap: direct/public **pre-quote request** conversation and general connector thread continuation are not yet a clean shared contract.

### Existing AI

Already exists in multiple product paths, including:

- RequestQuote/voice intake
- `POST /api/v1/quotes/requests/ai-requirement-draft`
- connector extraction/parsing
- provider requirement-to-quote draft generation

Migration should be strangler/shadow based, not a big-bang rewrite.

## 2. Channel product policy

### Email

Purpose: mostly inbound asynchronous intake.

Default:

- ingest
- understand
- if enough information exists, progress normally
- if incomplete, draft clarification questions

Optional tenant setting:

`automaticPreQuoteEmailClarification = true`

When enabled, Quixo may send low-risk clarification questions automatically.

Never automatic over email:

- price/discount
- availability promise
- binding scope
- acceptance of terms
- quotation send
- provider award/selection
- safety-sensitive advice requiring human escalation

Prefer one concise batch of high-value questions instead of many back-and-forth messages.

### Web widget

Purpose: live requirement finalisation.

Target UX:

1. user describes need
2. Expert Agent interprets
3. widget asks one/few focused questions
4. package is updated after every turn
5. customer sees structured summary
6. customer corrects/confirms
7. Quixo creates/submits canonical request

This should be the first synchronous proof.

### WhatsApp

Purpose: primary interactive asynchronous channel.

Target:

- text conversation first
- stable thread/request binding
- multiple clarification turns
- Quixo Messaging performs actual replies
- observe 24-hour service window/template requirements
- add audio transcription next
- add image/document understanding later

Current code gap to retire:

- WhatsApp category extraction returns `null`
- WhatsApp location extraction returns `null`
- audio message id is currently used as body text instead of transcription

### Marketplace

Purpose: interactive sourcing.

Demand side:

- requirement-building assistant
- category/service understanding
- scope refinement
- location/context completeness
- risk/inspection/readiness

Provider side:

- explain requirement
- surface missing information/risk
- prepare provider-reviewable proposal structure

Canonical sourcing relationship remains:

`Marketplace -> RequestQuote`

## 3. New Expert Agent contract

### Proposed endpoint

`POST /v1/expert/requirements/turn`

This endpoint should be channel-neutral.

Request shape (conceptual):

```json
{
  "schemaVersion": "1.0",
  "productSurface": "requestquote|marketplace|sendquote|widget|connector",
  "channel": "web|email|whatsapp|marketplace|voice|messenger",
  "message": {
    "externalMessageId": "...",
    "externalThreadId": "...",
    "text": "...",
    "media": []
  },
  "actorContext": {
    "providerCompanyId": null,
    "buyerOrganizationId": null,
    "identityUserId": null,
    "publicReference": null
  },
  "businessReferences": {
    "serviceRequestId": null,
    "quotationId": null
  },
  "priorExpertState": {
    "packageId": null,
    "packageVersion": null
  }
}
```

Response shape (conceptual):

```json
{
  "requirementPackage": {},
  "directive": "ask_clarification|ready_for_pricing|needs_human_review|inspection_required|safety_escalation",
  "clarificationQuestions": [],
  "replyDraft": null,
  "provenance": {
    "skillVersions": {},
    "model": "...",
    "analysisId": "..."
  }
}
```

The endpoint does not send anything and does not mutate Quixo.

## 4. New/extended Quixo contracts likely required

Exact routes should be confirmed in a bounded Quotes implementation slice.

### Q1 — Expert context projection

Proposed internal shape:

`GET /api/v1/quotes/internal/requests/{requestId}/expert-context`

Purpose:

- return minimum authorised request context
- include current request/version/category/location/contact-presence facts
- include relevant clarification/conversation references
- exclude unrelated secrets/internal DB details

This prevents the Expert Agent from querying QuoteService storage.

### Q2 — Expert evidence attachment

Proposed internal shape:

`POST /api/v1/quotes/internal/requests/{requestId}/expert-evidence`

Purpose:

- attach accepted Requirement Intelligence Package reference/version
- store readiness/directive/provenance needed by Quixo
- idempotent by analysis/package identity
- must not directly alter award, price, routing or quote state

A projection/reference may be preferable to copying the entire package; choose during contract design.

### Q3 — Pre-quote public/direct conversation

Current public conversation is Quotation-linked. A request-level surface is needed before a quote exists.

Candidate shape:

- `GET /api/v1/quotes/public/requests/{trackingToken}/conversation`
- `POST /api/v1/quotes/public/requests/{trackingToken}/conversation/messages`

Requirements:

- token-scoped
- non-governed/public only
- rate-limited
- preserves request identity
- does not expose provider/buyer internal data

Governed buyer clarifications keep their existing separate authority model.

### Q4 — Product-authorized clarification dispatch

Do **not** expose a generic "agent send to address" route.

Candidate QuoteService/internal operation:

`POST /api/v1/quotes/internal/requests/{requestId}/clarifications/dispatch`

Input:

- expert analysis/reference id
- approved draft content
- channel intent
- idempotency key

QuoteService/product code:

- verifies request/tenant/product policy
- resolves recipient from canonical state
- checks automatic-clarification setting
- chooses permitted Messaging operation
- sends through `IMessagingClient`
- records UMID/correlation
- returns delivery acceptance/status reference

### Q5 — Connector thread binding / continuation

The connector pipeline needs a durable way to say:

`external thread/message -> existing ServiceRequest`

instead of treating every new inbound message as a new lead.

For email, preserve:

- Message-ID
- In-Reply-To
- References
- normalized provider/thread identity

For WhatsApp, preserve:

- sender WA id
- tenant/company
- Meta message id
- stable conversation/request binding

For widget/Marketplace, use the product session/request reference.

This can be implemented as a dedicated binding aggregate or as carefully governed fields around the current intake model; decide only after current DB/domain review.

### Q6 — Expert readiness/read model

Provider-facing/request-routing logic needs a deterministic answer to:

- still clarifying
- ready for provider pricing
- inspection required
- human review required
- safety escalation

Do not overload `ServiceRequestStatus` unless the existing product lifecycle clearly supports that semantic.

Prefer a separate expert/readiness projection first.

## 5. Existing endpoints/contracts to keep

Use, do not duplicate:

- `POST /api/v1/quotes/internal/requests`
- `GET /api/v1/providers/internal/search`
- `GET /api/v1/providers/internal/company/{companyId}`
- Messaging email send/status APIs
- QuoteService `IMessagingClient`
- existing WhatsApp send methods/window policy
- existing quote conversation APIs
- existing governed buyer clarification APIs

## 6. Recommended delivery order

### Slice 1 — contracts only

- implement `RequirementConversationTurn`
- implement Requirement Intelligence Package v1
- unit/contract tests
- no Quixo calls

### Slice 2 — widget proof

- add Expert Agent client to widget/RequestQuote path
- progressive clarification
- structured confirmation
- existing request submit remains authoritative

Reason: easiest place to prove interactive quality without external channel delivery complexity.

### Slice 3 — request continuation contracts

- Q1 expert context projection
- Q2 expert evidence attachment
- Q3 pre-quote public request conversation
- Q5 external-thread binding

### Slice 4 — WhatsApp text

- replace null category/location parsing with Expert Agent
- bind replies to same request
- Q4 product-authorized clarification dispatch
- use existing window-aware Messaging
- full idempotency/audit proof

### Slice 5 — WhatsApp audio

- fetch media through owning connector
- transcribe
- pass transcript as evidence to same expert turn
- never use media id as requirement text

### Slice 6 — email

- replace/augment regex parsing using Expert Agent
- preserve thread headers
- tenant opt-in automatic clarification
- single clarification batch policy
- reply continues same request

### Slice 7 — Marketplace

- demand-side interactive refinement
- provider-side request intelligence
- no award/quote authority transfer

### Slice 8 — SendQuote expert proposal delegation

- Commercial Proposal Package
- shadow existing `RequirementQuoteAgentService`
- compare provider corrections/quality
- migrate only when evidence shows improvement

## 7. Learning evidence to capture from day one

For each channel:

- original customer/provider statement
- questions chosen by the agent
- customer replies
- requirement package versions
- human/provider edits
- time/turns to pricing-ready
- abandoned clarification
- safety/inspection escalations
- quote changes attributable to scope correction
- accepted commercial outcome when allowed
- skill/model versions

This turns real channel conversations into controlled expert-improvement evidence without letting them directly change production skills.

## 8. Explicitly deferred

- direct SendGrid/Twilio integration from `ai-agent-serve`
- Messenger/social transport implementation until the base turn contract is proven
- image/document reasoning until text + WhatsApp voice flows are stable
- automatic pricing/quote sending
- autonomous provider selection/award
- Task Scheduler/workforce integration
