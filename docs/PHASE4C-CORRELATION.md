# Phase 4C correlation persistence

## Purpose

HTTP correlation IDs are already server-generated, returned in the
`X-Correlation-ID` response header and emitted in privacy-safe structured
request logs. This slice persists that same request-scoped identifier into
business history so an operator can trace an HTTP transaction into the rows it
created or changed.

## Identity model

Two identifiers serve different purposes:

- `request_id` identifies one service or quotation request across its entire
  business lifecycle.
- `correlation_id` identifies one HTTP transaction.

A single business request can therefore accumulate many correlation IDs as the
customer replies, an operator decides, or a tool runs.

## Persistence

Migration `004_phase4c_correlation_persistence.sql` adds nullable UUID
`correlation_id` columns to:

- `agent_requests`
- `agent_messages`
- `agent_events`

Indexes are created on all three columns for trace lookup.

Existing historical rows remain `NULL`. Non-HTTP or future background work can
also persist `NULL` because there is no request-scoped correlation context.

## Propagation

The HTTP middleware owns correlation ID generation. Database helpers read the
current server-owned context and persist it automatically:

- initial request creation stores the inbound HTTP correlation ID
- customer/operator messages store the correlation ID of the HTTP call that
  accepted the message
- all audit events written during that call inherit the same correlation ID

Clients cannot supply or override this stored value through request bodies or
headers.

## Migration

Apply the migration before deploying code that writes the new columns:

```bash
docker exec -i agent-postgres \
  psql -U agentuser -d agentdb \
  < migrations/004_phase4c_correlation_persistence.sql
```

The migration is additive and idempotent.

## Trace example

After handling an HTTP request, use its `X-Correlation-ID` value to locate
related persistence records:

```sql
SELECT id, status, correlation_id
FROM agent_requests
WHERE correlation_id = '<correlation-uuid>'::uuid;

SELECT id, request_id, role, correlation_id
FROM agent_messages
WHERE correlation_id = '<correlation-uuid>'::uuid;

SELECT id, request_id, event_type, actor, correlation_id
FROM agent_events
WHERE correlation_id = '<correlation-uuid>'::uuid
ORDER BY created_at;
```

This provenance is operational metadata only. Request bodies, API keys and
exception messages remain excluded from structured request logs.
