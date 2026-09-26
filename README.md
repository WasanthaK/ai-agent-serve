# Mac Mini AI Agent Server

A lightweight, Docker-based AI agent server built with FastAPI, OpenAI and PostgreSQL.

The project demonstrates how a low-resource Mac Mini can operate as an always-on AI orchestration node while model inference runs in the cloud or, later, on a separate GPU server.

## What it does

The server can:

- Receive quote requests through a webhook
- Analyse requests using strict structured output
- Identify essential missing information
- Generate customer follow-up questions
- Maintain persistent workflow state
- Escalate sensitive requests for human review
- Approve or reject requests
- Accept and store customer replies
- Reanalyse the complete conversation
- Execute explicitly registered tools
- Restrict tools according to workflow status
- Apply category-specific intake and escalation profiles
- Publish the service taxonomy through a read-only endpoint
- Preserve a chronological audit trail

## Architecture

```text
Incoming request
      |
      v
Structured AI analysis
      |
      +--> Missing information --> Follow-up draft --> Customer reply
      |
      +--> Human review --> Approve / reject
      |
      v
Persistent workflow state
      |
      v
Controlled tools
      |
      v
Audit events
```

The Mac Mini coordinates the workflow. It is not required to run a large language model locally.

See [Agent Architecture](docs/AGENT-ARCHITECTURE.md) for the full design and the [Technical Roadmap](docs/TECHNICAL-ROADMAP.md) for the planned service-delivery agent platform.

## Technology

- Ubuntu Server
- Docker and Docker Compose
- Python
- FastAPI
- Uvicorn
- OpenAI Responses API
- PostgreSQL 16
- Psycopg 3

## Project structure

```text
agent-server/
├── app.py
├── db.py
├── tools.py
├── agent_skills/
│   ├── base.py
│   ├── definitions.py
│   ├── registry.py
│   └── service_catalog.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── migrations/
│   ├── 001_phase3_workflow.sql
│   └── 002_phase3_customer_replies.sql
├── tests/
│   ├── smoke_phase3.py
│   └── smoke_phase4.py
└── docs/
    ├── AGENT-ARCHITECTURE.md
    ├── INSTALLATION.md
    ├── TECHNICAL-ROADMAP.md
    └── TROUBLESHOOTING.md
```

## Workflow states

| Status | Meaning |
|---|---|
| `needs_information` | Essential customer information is missing |
| `awaiting_human_review` | A human decision is required |
| `ready` | Sufficient information is available |
| `approved` | A human approved an escalated request |
| `rejected` | A human rejected the request |
| `actioned` | Reserved for a completed external action |

Invalid transitions are rejected with HTTP `409 Conflict`.

## Structured analysis

Each request is converted into:

- `intent`
- `category`
- `summary`
- `urgency`
- `next_action`
- `needs_human_review`
- `missing_information`
- `follow_up_questions`

## Persistent data

PostgreSQL stores three related record types:

- `agent_requests` — original request, current analysis and status
- `agent_messages` — later customer or workflow messages
- `agent_events` — append-only workflow and tool history

Every request receives a UUID.

## Reusable skills

Service-delivery reasoning is packaged as versioned skills rather than one hardcoded prompt. The initial registry contains:

- `request_intake`
- `request_clarification`
- `safety_triage`
- `customer_communication`

The registry composes the strict output schema and model instructions, rejects duplicate names and detects conflicting field definitions. See [Skills Architecture](docs/SKILLS.md).

The service catalogue adds 47 selectable domain profiles. Seven group headers
remain non-selectable. Each profile provides focused intake topics and
domain-specific escalation signals without duplicating shared workflow skills.

## Controlled tools

The current tool registry contains:

```text
prepare_customer_follow_up
```

It prepares a draft response from the stored follow-up questions. It does not send the message.

The tool can run only when:

```text
status = needs_information
```

Rejected or otherwise incompatible requests cannot execute it.

## Main API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | Health and version |
| `GET` | `/service-catalog` | Retrieve service groups and skill profiles |
| `POST` | `/agent` | Direct structured analysis |
| `POST` | `/webhook/quote-request` | Create and analyse a request |
| `GET` | `/requests/{request_id}` | Retrieve the current request |
| `GET` | `/requests/{request_id}/messages` | Retrieve conversation history |
| `GET` | `/requests/{request_id}/events` | Retrieve audit history |
| `POST` | `/requests/{request_id}/reply` | Save a customer reply and reanalyse |
| `POST` | `/webhook/quote-request/{request_id}/reply` | Save a reply from the owning inbound channel |
| `POST` | `/requests/{request_id}/approve` | Approve a reviewed request |
| `POST` | `/requests/{request_id}/reject` | Reject an active request |
| `POST` | `/requests/{request_id}/tools/{tool_name}` | Execute an allowed tool |

Interactive API documentation is available at:

```text
http://localhost:8000/docs
```

## Quick start

Copy the environment template:

```bash
cp .env.example .env
```

Add the required secrets to `.env`, then start the services:

```bash
docker compose up -d --build
```

Check service health:

```bash
docker compose ps
curl http://localhost:8000/
```

Expected response:

```json
{
  "status": "running",
  "service": "agent-server",
  "version": "3.3.0"
}
```

For complete setup instructions, see [Installation Guide](docs/INSTALLATION.md).

## Database migrations

For an existing PostgreSQL container:

```bash
docker exec -i agent-postgres \
  psql -U agentuser -d agentdb \
  < migrations/001_phase3_workflow.sql

docker exec -i agent-postgres \
  psql -U agentuser -d agentdb \
  < migrations/002_phase3_customer_replies.sql
```

The migrations are idempotent and can be rerun safely.

## Phase 3 smoke test

Run the end-to-end workflow test while the containers are running:

```bash
python3 tests/smoke_phase3.py
```

The test verifies service health, missing-information detection, controlled follow-up drafting, conversational reanalysis, persistence, audit events, safety escalation, human approval and invalid-transition protection.

The smoke test creates test records in PostgreSQL and makes live model calls.
Export `AGENT_INBOUND_API_KEY` and `AGENT_OPERATOR_API_KEY` in the shell running
the smoke test. The operator value must match an entry in the server's
`AGENT_OPERATOR_CREDENTIALS` with all five permissions; the server does not
read `AGENT_OPERATOR_API_KEY`.

## Phase 4 skill smoke test

After deploying version 3.3.0, run:

```bash
python3 tests/smoke_phase4.py
```

This verifies the published catalogue, strict plumbing classification,
profile-guided clarification and dangerous electrical escalation. It creates
two test records and makes two live model calls.

## Security

Never commit `.env` or real API credentials.

Phase 4B requires separate `X-API-Key` credentials. The inbound key can create
requests at `/webhook/quote-request` only for the configured
`AGENT_INBOUND_SOURCE` and submit replies only for requests owned by that
source. Individual operator keys grant `read`, `analyze`, `reply`, `decide`
and/or `tools` permissions. The health and service-catalogue endpoints are
public. Decision, tool and reply events identify the authenticated operator
instead of trusting a name supplied in the request body. See
[Installation Guide](docs/INSTALLATION.md)
for key setup and [Phase 4B slices](docs/PHASE4B-SECURITY.md) for the remaining
security work.

Denied access is recorded in the container log using fixed event codes and
route templates, without request bodies or credentials. Model and tool failures
return generic details; tool drafts are not duplicated in the request audit
history.

These security slices are intended for controlled testing. The Compose API
port binds to the Mac Mini's loopback interface. For access from another
computer, use an SSH tunnel as described in the
[Phase 4B deployment guide](docs/PHASE4B-DEPLOYMENT.md). An external webhook
requires a separately configured private TLS ingress and request controls.

## Development history

- Phase 1 — Dockerised FastAPI agent with structured AI analysis
- Phase 2 — PostgreSQL persistence and UUID request tracking
- Phase 3A — Workflow states, human review and event history
- Phase 3B — Registered, state-aware tools
- Phase 3C — Persistent customer replies and conversational reanalysis

## Roadmap

The next stage introduces reusable service-delivery skills, authentication, authorization, observability and a channel-neutral request inbox. Later phases add provider routing, quotation workflows, delivery coordination and service closure.

See the complete [Technical Roadmap](docs/TECHNICAL-ROADMAP.md).
