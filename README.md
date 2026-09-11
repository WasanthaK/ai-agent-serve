# AI Agent Server

A lightweight, Docker-based AI agent server built with FastAPI, OpenAI and PostgreSQL.

This project demonstrates a practical pattern for using low-resource edge hardware as an always-on **AI orchestration node**, while model inference can run in the cloud or on a separate GPU server.

## Architecture

```text
Website / App / Messaging / Webhook
              |
              v
       FastAPI Agent Server
              |
       AI classification
              |
       Structured decision
              |
        PostgreSQL state
              |
       Human review / tools
```

## Current capabilities

- FastAPI REST API
- Docker and Docker Compose deployment
- OpenAI-powered request analysis
- Structured JSON output
- Quote-request webhook
- PostgreSQL persistence
- UUID request tracking
- Human-review flag and workflow status
- Container health checks
- Resource limits suitable for small servers

## Example

A request such as:

```text
My kitchen tap is leaking badly and I need someone today.
```

can be transformed into structured data containing:

- intent
- category
- summary
- urgency
- next action
- whether human review is required

The request and AI analysis are then persisted in PostgreSQL.

## Quick start

See [Installation Guide](docs/INSTALLATION.md).

For the architecture and design decisions, see [Agent Architecture](docs/AGENT-ARCHITECTURE.md).

For problems encountered during the real build, see [Troubleshooting](docs/TROUBLESHOOTING.md).

## Security

Never commit a real `.env` file. Copy `.env.example` to `.env` and supply your own credentials locally.

## Roadmap

Next stages include human approval/rejection endpoints, action tools, authentication, observability, MCP integration, channel adapters, and optional local GPU inference.
