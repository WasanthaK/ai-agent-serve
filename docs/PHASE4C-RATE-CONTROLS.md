# Phase 4C rate controls

## Purpose

The agent limits authenticated request volume before protected route logic can invoke model processing, workflow mutations, tools, or database writes.

## Default limits

Two independent rolling 60-second limits are configured:

- `AGENT_INBOUND_RATE_LIMIT_PER_MINUTE`: default `60`
- `AGENT_OPERATOR_RATE_LIMIT_PER_MINUTE`: default `120`

Each value must be an integer between `1` and `10000`. Invalid configuration fails application import/startup rather than silently disabling the control.

## Identity model

Rate limits are keyed only by server-controlled authenticated identity:

- inbound requests use `channel:<configured-source>`, for example `channel:website`
- operator requests use `operator:<stable-operator-id>`

Raw API keys are never used as bucket identifiers or written to logs.

Key rotation does not create additional quota. Multiple valid keys belonging to the same inbound channel or operator share the same bucket.

Invalid or missing credentials retain the existing `401` behavior and do not consume authenticated quota. Operator requests that fail permission checks retain the existing `403` behavior and do not consume authorized quota.

## Enforcement

The limiter uses an in-memory rolling 60-second window. A request is accepted while the bucket contains fewer than the configured number of requests in the current window.

When the limit is exceeded, the response is:

```json
{"detail":"Rate limit exceeded"}
```

with HTTP status `429` and a `Retry-After` header containing the number of seconds until capacity becomes available.

The existing outer correlation middleware still adds `X-Correlation-ID` and records the privacy-safe request outcome.

## Current deployment scope

This implementation is intentionally scoped to the current single `agent-server` process. The limiter state exists only in that process and resets on restart.

If the service is later scaled to multiple concurrent agent processes or replicas, replace the in-memory limiter with shared coordination/storage so all replicas enforce one combined quota.

## Configuration

The defaults require no `.env` change. Optional overrides are:

```text
AGENT_INBOUND_RATE_LIMIT_PER_MINUTE=60
AGENT_OPERATOR_RATE_LIMIT_PER_MINUTE=120
```

Rebuild/restart the agent container after changing these values.
