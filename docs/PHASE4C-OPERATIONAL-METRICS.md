# Phase 4C operational metrics

## Purpose

The agent maintains lightweight, privacy-safe operational metrics for the current single `agent-server` process.

This slice measures HTTP/service operation only. Model-call latency and model-call failure metrics remain a separate Phase 4C capability.

## Protected endpoint

Operational metrics are available at:

```text
GET /metrics/operational
```

The endpoint requires the existing operator `read` permission. It is not public.

The endpoint returns JSON with:

- process uptime in seconds
- total completed/failed HTTP requests observed by the middleware
- exception count
- total and maximum request duration in milliseconds
- counts by HTTP status code
- counts by HTTP status class
- counts by HTTP method
- counts by FastAPI route template
- request-size (`413`) rejection count
- rate-limit (`429`) rejection count

## Privacy and metric cardinality

Metrics contain aggregate operational values only.

They do not contain:

- customer names or messages
- request IDs or correlation IDs
- raw URL paths containing UUIDs
- query strings
- API keys
- operator identities
- exception messages

Dynamic paths are aggregated by FastAPI route template, for example:

```text
/requests/{request_id}
```

rather than by the concrete UUID URL. Requests rejected before routing may appear under the bounded `<unresolved>` route label.

## Process scope

Metrics live in memory and reset when the `agent-server` process restarts. This matches the current single-process deployment and keeps the Mac Mini orchestration node lightweight.

If persistent historical dashboards or multiple concurrent agent replicas are introduced later, export these aggregates to a shared monitoring backend rather than using request-level labels.

## Counting semantics

A metrics request itself is recorded like every other HTTP request. The JSON snapshot is taken before that metrics request completes, so the response represents all previously completed requests plus any previously recorded exceptions.

Unhandled middleware exceptions increment `requests_total` and `exceptions_total`. Completed responses are grouped by their actual status code, including `413` and `429` control rejections.

## Next observability slice

The next Phase 4C item is model-call latency and failure metrics. Those metrics should be added around the OpenAI call boundary without including model prompts, customer content, or raw exception messages.
