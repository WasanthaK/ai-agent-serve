# Agent Architecture

## Design principle

The Mac Mini is a lightweight, always-on orchestration node. It receives requests, coordinates AI analysis, maintains workflow state, invokes approved tools and records every significant event.

Large-model inference remains external and can be provided by a cloud model or, later, a separate GPU workstation.

## System architecture

```text
Website / App / Messaging Channel
                |
                v
      POST /webhook/quote-request
                |
                v
        FastAPI Agent Server
                |
                v
       Structured AI analysis
                |
       +--------+---------+
       |                  |
       v                  v
Missing information   Human review
       |                  |
       v                  v
Follow-up draft      Approve / reject
       |                  |
       v                  |
Customer reply            |
       |                  |
       +--------+---------+
                |
                v
          Reanalysis
                |
                v
      PostgreSQL state + events
                |
                v
        Controlled tool layer
```

## Structured analysis

The model returns strict JSON rather than unstructured prose. Current fields are:

- `intent`
- `category`
- `summary`
- `urgency`
- `next_action`
- `needs_human_review`
- `missing_information`
- `follow_up_questions`

The application uses these fields to calculate workflow status and determine which actions are permitted.

## Workflow states

### `needs_information`

Essential information is missing. The agent can prepare a customer follow-up draft.

### `awaiting_human_review`

The request is urgent, dangerous, high-value, legally sensitive or unusual. A human must approve or reject it.

### `ready`

The agent has enough information and no mandatory human review is required.

### `approved`

A human approved a request that required review.

### `rejected`

A human rejected the request. Further workflow tools are blocked.

### `actioned`

Reserved for a future external action that completed successfully.

## Status selection

Status is derived in this order:

1. If essential information is missing, use `needs_information`.
2. Otherwise, if human review is required, use `awaiting_human_review`.
3. Otherwise, use `ready`.

This allows missing information to be collected before a later escalation decision.

## Persistent conversation

The initial customer request remains in `agent_requests.message`. Later replies are stored separately in `agent_messages`.

During reanalysis, the server combines the original request with all stored replies in chronological order. The model analyses the complete conversation and should not ask again for information already supplied.

## Human in the loop

Requests in `awaiting_human_review` can be approved through:

```text
POST /requests/{request_id}/approve
```

Active requests can be rejected through:

```text
POST /requests/{request_id}/reject
```

Invalid transitions return HTTP `409 Conflict`.

## Controlled tool layer

Tools are registered explicitly in `tools.py`. The current registry contains:

```text
prepare_customer_follow_up
```

This tool:

- Runs only when status is `needs_information`
- Uses stored follow-up questions
- Produces a customer-friendly draft
- Marks the result as `draft_only`
- Does not send anything externally

A tool absent from the registry cannot execute. A registered tool also cannot execute from an unauthorised workflow state.

## Audit events

Important activity is appended to `agent_events`. Current event types include:

- `request_created`
- `customer_message_received`
- `request_reanalysed`
- `request_approved`
- `request_rejected`
- `tool_started`
- `tool_completed`
- `tool_failed`
- `reanalysis_failed`

Each event records an event UUID, request UUID, event type, actor, JSON details and creation timestamp.

## Database model

### `agent_requests`

Stores the original request, current analysis and current workflow state.

### `agent_messages`

Stores later conversation messages linked to the request.

### `agent_events`

Stores an append-only history of workflow decisions and tool activity.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | Health and version |
| `POST` | `/agent` | Direct structured analysis |
| `POST` | `/webhook/quote-request` | Create and analyse a request |
| `GET` | `/requests/{request_id}` | Retrieve current state |
| `GET` | `/requests/{request_id}/messages` | Retrieve conversation history |
| `GET` | `/requests/{request_id}/events` | Retrieve audit history |
| `POST` | `/requests/{request_id}/reply` | Save a reply and reanalyse |
| `POST` | `/requests/{request_id}/approve` | Approve a reviewed request |
| `POST` | `/requests/{request_id}/reject` | Reject an active request |
| `POST` | `/requests/{request_id}/tools/{tool_name}` | Execute an allowed tool |

## Failure handling

A customer reply is stored before AI reanalysis begins. If the model call fails:

- The customer message remains stored.
- A `reanalysis_failed` event is recorded.
- The endpoint returns HTTP `502`.
- Reanalysis can be retried without losing the reply.

Tool failures similarly create a `tool_failed` event.

## Deployment

The Docker Compose deployment includes:

- FastAPI and Uvicorn
- PostgreSQL 16
- Container health checks
- Persistent PostgreSQL storage
- Memory limits suitable for the Mac Mini

Database changes are stored as versioned SQL migrations in `migrations/`.

## Security boundary

The current system is suitable for local development and controlled testing. Before public exposure it requires:

- Webhook authentication
- API authentication and authorisation
- Secret rotation
- HTTPS through a reverse proxy or secure tunnel
- Rate limiting
- Request-size controls
- Restricted network exposure
- Production logging and monitoring

## Verification

The end-to-end Phase 3 smoke test is:

```bash
python3 tests/smoke_phase3.py
```

It verifies the controlled workflow, conversation loop, tool restrictions, safety escalation, approvals, persistence and audit history.

## Future integrations

The controlled tool layer can later support Quixo operations, email and messaging adapters, WhatsApp, CRM actions, scheduling, MCP servers, external APIs and separate GPU-based local inference.

Every future tool should remain registered, state-aware, auditable and restricted according to its risk.
