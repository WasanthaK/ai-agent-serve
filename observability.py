"""Request-scoped observability primitives with privacy-safe structured logs."""

import json
import logging
import time
from contextvars import ContextVar
from uuid import uuid4

from starlette.responses import PlainTextResponse


request_logger = logging.getLogger("agent.requests")
request_logger.setLevel(logging.INFO)
if not request_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    request_logger.addHandler(_handler)
request_logger.propagate = False

_correlation_id = ContextVar("agent_correlation_id", default=None)


def get_correlation_id():
    """Return the correlation ID for the current request, if one exists."""
    return _correlation_id.get()


def _route_template(scope):
    route = scope.get("route")
    return getattr(route, "path", None)


def _log(event, **fields):
    request_logger.info(
        json.dumps(
            {"event": event, **fields},
            separators=(",", ":"),
            sort_keys=True,
        )
    )


async def correlation_exception_handler(request, exc):
    """Preserve the request correlation ID on otherwise unhandled 500s."""
    correlation_id = getattr(request.state, "correlation_id", None)
    headers = {}
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
    return PlainTextResponse(
        "Internal Server Error",
        status_code=500,
        headers=headers,
    )


class StructuredRequestLoggingMiddleware:
    """Assign a server-owned correlation ID and log HTTP request outcomes."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        correlation_id = str(uuid4())
        scope.setdefault("state", {})["correlation_id"] = correlation_id
        token = _correlation_id.set(correlation_id)
        started = time.perf_counter()
        status_code = None

        async def send_with_correlation(message):
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = message.get("status")
                headers = list(message.get("headers", []))
                headers.append(
                    (b"x-correlation-id", correlation_id.encode("ascii"))
                )
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            _log(
                "request_failed",
                correlation_id=correlation_id,
                method=scope.get("method"),
                route=_route_template(scope),
                duration_ms=duration_ms,
                error_type=type(exc).__name__,
            )
            raise
        else:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            _log(
                "request_completed",
                correlation_id=correlation_id,
                method=scope.get("method"),
                route=_route_template(scope),
                status_code=status_code,
                duration_ms=duration_ms,
            )
        finally:
            _correlation_id.reset(token)
