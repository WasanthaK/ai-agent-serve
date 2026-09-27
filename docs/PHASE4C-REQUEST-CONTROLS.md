# Phase 4C request-size control

## Purpose

The agent rejects oversized HTTP request bodies before FastAPI parses them or any route can invoke authentication dependencies, model processing, or database writes.

## Default limit

`AGENT_MAX_REQUEST_BYTES` controls the maximum accepted HTTP request body size in bytes.

- Default: `65536` bytes (64 KiB)
- Minimum: `1` byte
- Maximum configurable value: `10485760` bytes (10 MiB)

If the variable is absent, the 64 KiB default is used. Invalid, zero, negative, non-integer, or values above 10 MiB fail application import/startup rather than silently disabling the guardrail.

## Enforcement

The limit is enforced inside the existing structured-request correlation boundary.

- Requests whose valid `Content-Length` already exceeds the limit receive HTTP `413` immediately.
- Requests without a usable `Content-Length` are counted as ASGI body chunks are received.
- Chunked or streamed requests cannot exceed the same cumulative byte limit.
- A body exactly equal to the configured maximum is accepted.
- Rejected requests never reach FastAPI route code.

The rejection response is:

```json
{"detail":"Request body too large"}
```

with HTTP status `413`.

## Correlation and privacy

Because the limiter runs inside `StructuredRequestLoggingMiddleware`, a rejected request still receives the server-generated `X-Correlation-ID` response header and a privacy-safe structured request log with status `413`.

The request body, API keys and query-string values are not included in the structured log.

## Configuration

To override the default, add a byte value to `.env`, for example:

```text
AGENT_MAX_REQUEST_BYTES=131072
```

Then rebuild/restart the agent container. The current deployment does not require this setting because the default applies automatically.
