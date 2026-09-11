# Agent Architecture

## Design principle

The server is an orchestration node rather than a large-model inference machine.

```text
Incoming request
      |
      v
FastAPI webhook
      |
      v
AI analysis
      |
      v
Structured JSON
      |
      v
PostgreSQL persistence
      |
      +--> ready
      |
      +--> awaiting_human_review
                 |
                 v
           approve / reject
                 |
                 v
              action
```

## Why structured output matters

The model should not merely produce prose. The application needs predictable fields that downstream code can evaluate.

Current analysis fields include:

- `intent`
- `category`
- `summary`
- `urgency`
- `next_action`
- `needs_human_review`

## Persistence

Each incoming webhook receives a UUID. The original request and AI analysis are stored in PostgreSQL with a workflow status.

This changes the system from a stateless chatbot into the beginning of a durable agent workflow.

## Human in the loop

Potentially consequential or uncertain requests can be marked `needs_human_review=true`. These requests enter `awaiting_human_review` rather than automatically taking action.

The next implementation stage is explicit approval and rejection endpoints.

## Future tool layer

Approved work can later invoke tools such as:

- Quixo operations
- email or messaging
- CRM actions
- MCP servers
- scheduling
- local services
- external APIs

## Distributed inference

The orchestration host can remain lightweight. Model inference can be supplied by a cloud model or a separate GPU workstation running local models.
