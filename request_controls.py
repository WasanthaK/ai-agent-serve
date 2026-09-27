"""Deterministic HTTP request controls for the agent service."""

import math
import os
import threading
import time
from collections import deque

from starlette.responses import JSONResponse


DEFAULT_MAX_REQUEST_BYTES = 64 * 1024
MAX_CONFIGURABLE_REQUEST_BYTES = 10 * 1024 * 1024
DEFAULT_INBOUND_RATE_LIMIT_PER_MINUTE = 60
DEFAULT_OPERATOR_RATE_LIMIT_PER_MINUTE = 120
MAX_CONFIGURABLE_RATE_LIMIT_PER_MINUTE = 10000


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


def load_rate_limit(env_name, default):
    """Load and validate one per-minute request limit."""
    raw = os.getenv(env_name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{env_name} must be an integer") from exc

    if value <= 0 or value > MAX_CONFIGURABLE_RATE_LIMIT_PER_MINUTE:
        raise RuntimeError(f"{env_name} must be between 1 and 10000 requests per minute")
    return value


class RollingWindowRateLimiter:
    """Thread-safe in-memory rolling-window limiter keyed by server-owned identity."""

    def __init__(self, limit, window_seconds=60.0, clock=None):
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = limit
        self.window_seconds = float(window_seconds)
        self.clock = clock or time.monotonic
        self._buckets = {}
        self._lock = threading.Lock()

    def check(self, identity):
        """Return None if allowed, otherwise integer Retry-After seconds."""
        now = self.clock()
        cutoff = now - self.window_seconds

        with self._lock:
            bucket = self._buckets.get(identity)
            if bucket is None:
                bucket = deque()
                self._buckets[identity] = bucket

            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= self.limit:
                retry_after = math.ceil((bucket[0] + self.window_seconds) - now)
                return max(1, retry_after)

            bucket.append(now)
            return None


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
