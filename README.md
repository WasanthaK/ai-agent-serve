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
│   └── smoke_phase3.py
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
| `POST` | `/agent` | Direct structured analysis |
| `POST` | `/webhook/quote-request` | Create and analyse a request |
| `GET` | `/requests/{request_id}` | Retrieve the current request |
| `GET` | `/requests/{request_id}/messages` | Retrieve conversation history |
| `GET` | `/requests/{request_id}/events` | Retrieve audit history |
| `POST` | `/requests/{request_id}/reply` | Save a customer reply and reanalyse |
| `POST` | `/requests/{request_id}/approve` | Approve a reviewed request |
| `POST` | `/requests/{request_id}/reject` | Reject an active request |
| `POST` | `/requests/{request_id}/tools/{tool_name}` | Execute an allowed tool |

Interactive API documentation is available at:

```text
http://SERVER_ADDRESS:8000/docs
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
  "version": "3.1.0"
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

## Security

Never commit `.env` or real API credentials.

The current implementation is intended for local development and controlled testing. Before public exposure, add API and webhook authentication, HTTPS, authorisation, rate limiting, request-size limits, production monitoring and secret rotation.

## Development history

- Phase 1 — Dockerised FastAPI agent with structured AI analysis
- Phase 2 — PostgreSQL persistence and UUID request tracking
- Phase 3A — Workflow states, human review and event history
- Phase 3B — Registered, state-aware tools
- Phase 3C — Persistent customer replies and conversational reanalysis

## Roadmap

The next stage introduces reusable service-delivery skills, authentication, authorization, observability and a channel-neutral request inbox. Later phases add provider routing, quotation workflows, delivery coordination and service closure.

See the complete [Technical Roadmap](docs/TECHNICAL-ROADMAP.md).
