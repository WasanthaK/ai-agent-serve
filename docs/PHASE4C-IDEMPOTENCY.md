# Phase 4C webhook idempotency

## Purpose

Inbound webhook providers can retry the same delivery after timeouts or lost
responses. `POST /webhook/quote-request` therefore supports an optional
`Idempotency-Key` header so a retry does not create a duplicate request or
repeat the model call.

The header remains optional during this compatibility phase. Existing clients
without the header continue to use the previous behavior.

## Contract

For a supplied `Idempotency-Key`:

- The raw key is never stored. The server stores a SHA-256 digest.
- The source, customer name and message are hashed as a canonical payload.
- The first delivery reserves a request UUID before model analysis starts.
- The completed delivery stores the request under that reserved UUID.
- An exact replay returns the original persisted request and skips model
  analysis and request insertion.
- Reusing the key for a different payload returns HTTP `409`.
- A duplicate received while the first delivery is still processing returns
  HTTP `409` with `Retry-After: 2`.
- If model analysis or request persistence fails before creation completes, the
  reservation is released so the sender can retry.

Idempotency is scoped by inbound source, so two independently authenticated
sources may use the same external key without colliding.

## Database migration

Apply the migration to an existing PostgreSQL container before deploying the
application code:

```bash
docker exec -i agent-postgres \
  psql -U agentuser -d agentdb \
  < migrations/003_phase4c_webhook_idempotency.sql
```

The migration is idempotent and creates `webhook_idempotency` plus a unique
index on its reserved request UUID.

The reservation table intentionally does not use a foreign key to
`agent_requests`: a request UUID is reserved before the request row exists.

## Example

```bash
curl -X POST http://localhost:8000/webhook/quote-request \
  -H "X-API-Key: $AGENT_INBOUND_API_KEY" \
  -H "Idempotency-Key: website-delivery-12345" \
  -H "Content-Type: application/json" \
  -d '{"source":"website","customer_name":"Test Customer","message":"My kitchen tap is leaking."}'
```

Repeating the same call with the same idempotency key and payload returns the
same `request_id` without another model call.

## Current boundary

This slice prevents duplicate processing for normal retries and concurrent
duplicate delivery. Recovery of reservations left in `processing` by a hard
process or host crash belongs to the next Phase 4C retry-safety slice.
