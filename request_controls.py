"""Deterministic HTTP request controls for the agent service."""

import os

from starlette.responses import JSONResponse


DEFAULT_MAX_REQUEST_BYTES = 64 * 1024
MAX_CONFIGURABLE_REQUEST_BYTES = 10 * 1024 * 1024


def load_max_request_bytes():
    """Load and validate the configured HTTP request-body limit."""
    raw = os.getenv("AGENT_MAX_REQUEST_BYTES", str(DEFAULT_MAX_REQUEST_BYTES)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("AGENT_MAX_REQUEST_BYTES must be an integer") from exc

    if value <= 0 or value > MAX_CONFIGURABLE_REQUEST_BYTES:
        raise RuntimeError(
            "AGENT_MAX_REQUEST_BYTES must be between 1 and 10485760 bytes"
        )
    return value


class RequestBodyLimitMiddleware:
    """Reject HTTP request bodies larger than the configured byte limit."""

    def __init__(self, app, max_bytes):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        content_length = None
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    content_length = int(value.decode("ascii"))
                except (UnicodeDecodeError, ValueError):
                    content_length = None
                break

        if content_length is not None and content_length > self.max_bytes:
            response = JSONResponse(
                {"detail": "Request body too large"},
                status_code=413,
            )
            await response(scope, receive, send)
            return

        messages = []
        total_bytes = 0

        while True:
            message = await receive()
            messages.append(message)

            if message.get("type") == "http.disconnect":
                break

            if message.get("type") != "http.request":
                continue

            total_bytes += len(message.get("body", b""))
            if total_bytes > self.max_bytes:
                response = JSONResponse(
                    {"detail": "Request body too large"},
                    status_code=413,
                )
                await response(scope, receive, send)
                return

            if not message.get("more_body", False):
                break

        index = 0

        async def replay_receive():
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)
