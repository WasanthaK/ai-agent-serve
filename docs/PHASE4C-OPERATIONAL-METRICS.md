# Phase 4C operational metrics

## Purpose

The agent maintains lightweight, privacy-safe operational metrics for the current single `agent-server` process.

The metrics cover both HTTP/service operation and aggregate model-provider calls used by request analysis.

## Protected endpoint

Operational metrics are available at:

```text
GET /metrics/operational
```

The endpoint requires the existing operator `read` permission. It is not public.

The endpoint returns JSON with HTTP metrics including:

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

It also returns aggregate `model_calls` metrics:

- `calls_total`
- `successes_total`
- `failures_total`
- `latency_ms_total`
- `latency_ms_average`
- `latency_ms_max`

## Model-call counting semantics

The measured boundary is the OpenAI provider call in `analyze_quote_request()`.

A model call is counted as successful when the provider call itself returns successfully. If later local processing fails, such as JSON parsing of the returned output, that does not retroactively convert the provider call into a provider failure. The request-analysis API still preserves its existing `502` failure contract for such processing failures.

If the provider call raises an exception, the call is counted as a model failure and the existing request-analysis `502` contract remains unchanged.

These metrics intentionally describe provider-call reliability and latency; they are not a measure of semantic model quality or end-to-end request-analysis success.

## Privacy and metric cardinality

Metrics contain aggregate operational values only.

They do not contain:

- customer names or messages
- prompts or model responses
- request IDs or correlation IDs
- raw URL paths containing UUIDs
- query strings
- API keys
- operator identities
- exception messages

Dynamic HTTP paths are aggregated by FastAPI route template, for example:

```text
/requests/{request_id}
```

rather than by the concrete UUID URL. Requests rejected before routing may appear under the bounded `<unresolved>` route label.

Model-call metrics have no request-level, customer-level, prompt-level, exception-message, or dynamically generated labels.

## Process scope

Metrics live in memory and reset when the `agent-server` process restarts. This matches the current single-process deployment and keeps the Mac Mini orchestration node lightweight.

If persistent historical dashboards or multiple concurrent agent replicas are introduced later, export these aggregates to a shared monitoring backend rather than using request-level labels.

## HTTP counting semantics

A metrics request itself is recorded like every other HTTP request. The JSON snapshot is taken before that metrics request completes, so the response represents all previously completed requests plus any previously recorded exceptions.

Unhandled middleware exceptions increment `requests_total` and `exceptions_total`. Completed responses are grouped by their actual status code, including `413` and `429` control rejections.

## Next Phase 4C slice

The next reliability/observability item in the technical roadmap is skill-version and tool-version recording.
