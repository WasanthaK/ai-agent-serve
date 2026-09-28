# Phase 4C health and readiness checks

## Purpose

The agent exposes separate liveness and readiness signals so operators and Docker can distinguish a running process from a service that can safely accept work.

## Endpoints

### `GET /health/live`

Liveness confirms that the FastAPI process is running.

It does not call PostgreSQL or any external dependency.

Example response:

```json
{
  "status": "alive",
  "service": "agent-server"
}
```

A liveness check should remain successful while the process is responsive even if PostgreSQL is temporarily unavailable.

### `GET /health/ready`

Readiness confirms that the process is running and PostgreSQL is reachable.

The readiness probe opens a short-lived PostgreSQL connection with a two-second connection timeout and executes `SELECT 1`.

Ready response:

```json
{
  "status": "ready",
  "service": "agent-server",
  "dependencies": {
    "database": "ready"
  }
}
```

If PostgreSQL cannot be reached or the probe fails, the endpoint returns HTTP `503` with the controlled response:

```json
{
  "detail": "Service is not ready"
}
```

Database host names, credentials and exception messages are not returned.

## Existing root endpoint

`GET /` remains unchanged for backward compatibility and still reports the service/version status.

## Docker health check

The agent container health check now targets `/health/ready` rather than `/`.

This means Docker reports the agent healthy only when both FastAPI and PostgreSQL are usable.

The PostgreSQL container continues to use `pg_isready`, and the agent service continues to depend on PostgreSQL reaching its own healthy state during startup.

## Scope

This capability does not change:

- API authentication or authorization
- workflow states or transitions
- model behavior
- tool authority
- database schema
- persisted business data

The health endpoints are public and contain only controlled operational metadata.

## Validation

Automated tests verify that:

- liveness is dependency-free
- readiness returns HTTP 200 when PostgreSQL is considered ready
- readiness returns HTTP 503 when PostgreSQL is unavailable
- readiness failures do not expose PostgreSQL or password details

The full test suite passed with 84 tests before PR creation.

## Live verification after merge

After deployment, verify:

```bash
curl -sS http://127.0.0.1:8000/health/live
curl -sS -i http://127.0.0.1:8000/health/ready
docker compose ps
```

The agent container should report healthy only after `/health/ready` succeeds.
