"""Fail-closed credentials and permissions for inbound and operator routes."""

import hashlib
import hmac
import json
import logging
import os
import re
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

from request_controls import (
    DEFAULT_INBOUND_RATE_LIMIT_PER_MINUTE,
    DEFAULT_OPERATOR_RATE_LIMIT_PER_MINUTE,
    RollingWindowRateLimiter,
    load_rate_limit,
)


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
OPERATOR_PERMISSIONS = frozenset({"read", "analyze", "reply", "decide", "tools"})
security_logger = logging.getLogger("agent.security")


def audit_denial(request: Request, reason: str, actor: str | None = None) -> None:
    """Log only server-controlled metadata; never inspect headers, URL or body."""
    route = request.scope.get("route")
    security_logger.warning(json.dumps({
        "event": "access_denied",
        "reason": reason,
        "method": request.method,
        "route": getattr(route, "path", "unknown"),
        "actor": actor,
    }, separators=(",", ":")))


@dataclass(frozen=True)
class OperatorPrincipal:
    id: str
    permissions: frozenset[str]

    @property
    def actor(self) -> str:
        return f"operator:{self.id}"


def _key_digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def _valid_key(value: object) -> bool:
    return isinstance(value, str) and len(value) >= 32 and not any(
        char.isspace() for char in value
    )


def _valid_channel(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}", value) is not None
    )


def load_inbound_source() -> str:
    source = os.getenv("AGENT_INBOUND_SOURCE", "")
    if not source or source != source.strip() or any(char.isspace() for char in source):
        raise RuntimeError("AGENT_INBOUND_SOURCE must be a nonempty source without whitespace")
    return source


def _load_inbound_entries() -> list[tuple[str, list[str]]]:
    configured = os.getenv("AGENT_INBOUND_CREDENTIALS", "")
    inbound_single = os.getenv("AGENT_INBOUND_API_KEY", "")
    inbound_multiple = os.getenv("AGENT_INBOUND_API_KEYS", "")
    legacy_source = os.getenv("AGENT_INBOUND_SOURCE", "")

    if configured:
        if inbound_single or inbound_multiple or legacy_source:
            raise RuntimeError(
                "Configure either AGENT_INBOUND_CREDENTIALS or legacy inbound settings"
            )
        try:
            entries = json.loads(configured)
        except ValueError as exc:
            raise RuntimeError("AGENT_INBOUND_CREDENTIALS must be a JSON array") from exc
        if not isinstance(entries, list) or not 1 <= len(entries) <= 20:
            raise RuntimeError(
                "AGENT_INBOUND_CREDENTIALS must contain between one and twenty channels"
            )

        normalized = []
        sources = set()
        for entry in entries:
            if (
                not isinstance(entry, dict)
                or set(entry) not in ({"source", "key"}, {"source", "keys"})
            ):
                raise RuntimeError(
                    "Each inbound channel requires source and key or keys"
                )
            source = entry["source"]
            keys = entry.get("keys", [entry.get("key")])
            if not _valid_channel(source) or source in sources:
                raise RuntimeError(
                    "Inbound channel sources must be unique normalized identifiers"
                )
            if (
                not isinstance(keys, list)
                or not 1 <= len(keys) <= 2
                or any(not _valid_key(key) for key in keys)
            ):
                raise RuntimeError(
                    "Configure one or two valid keys per inbound channel"
                )
            sources.add(source)
            normalized.append((source, keys))
        return normalized

    if inbound_multiple:
        if inbound_single:
            raise RuntimeError("Configure either AGENT_INBOUND_API_KEY or AGENT_INBOUND_API_KEYS")
        try:
            inbound_keys = json.loads(inbound_multiple)
        except ValueError as exc:
            raise RuntimeError("AGENT_INBOUND_API_KEYS must be a JSON array") from exc
    else:
        inbound_keys = [inbound_single]

    if (
        not isinstance(inbound_keys, list)
        or not 1 <= len(inbound_keys) <= 2
        or any(not _valid_key(key) for key in inbound_keys)
    ):
        raise RuntimeError("Configure one or two valid inbound API keys")

    return [(load_inbound_source(), inbound_keys)]


def load_credentials() -> tuple[
    tuple[tuple[bytes, str], ...],
    tuple[tuple[bytes, OperatorPrincipal], ...],
]:
    """Validate the full credential set before the API accepts traffic."""
    inbound_entries = _load_inbound_entries()

    try:
        entries = json.loads(os.getenv("AGENT_OPERATOR_CREDENTIALS", ""))
    except ValueError as exc:
        raise RuntimeError("AGENT_OPERATOR_CREDENTIALS must be a JSON array") from exc
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("AGENT_OPERATOR_CREDENTIALS must contain at least one operator")

    inbound_credentials = []
    credentials = []
    ids = set()
    digests = []

    for source, keys in inbound_entries:
        for key in keys:
            digest = _key_digest(key)
            if any(hmac.compare_digest(digest, existing) for existing in digests):
                raise RuntimeError("Inbound API keys must differ")
            digests.append(digest)
            inbound_credentials.append((digest, source))

    for entry in entries:
        if (
            not isinstance(entry, dict)
            or set(entry) not in (
                {"id", "key", "permissions"},
                {"id", "keys", "permissions"},
            )
        ):
            raise RuntimeError("Each operator requires id, key or keys, and permissions")
        operator_id = entry["id"]
        keys = entry.get("keys", [entry.get("key")])
        permissions = entry["permissions"]
        if (
            not isinstance(operator_id, str)
            or re.fullmatch(r"[a-zA-Z][a-zA-Z0-9._-]{0,63}", operator_id) is None
            or operator_id in ids
        ):
            raise RuntimeError("Operator IDs must be unique, stable identifiers")
        if (
            not isinstance(keys, list)
            or not 1 <= len(keys) <= 2
            or any(not _valid_key(key) for key in keys)
        ):
            raise RuntimeError("Configure one or two valid keys per operator")
        if (
            not isinstance(permissions, list)
            or not permissions
            or any(
                not isinstance(permission, str)
                or permission not in OPERATOR_PERMISSIONS
                for permission in permissions
            )
            or len(set(permissions)) != len(permissions)
        ):
            raise RuntimeError("Operator permissions must be unique known permissions")

        ids.add(operator_id)
        principal = OperatorPrincipal(operator_id, frozenset(permissions))
        for key in keys:
            digest = _key_digest(key)
            if any(hmac.compare_digest(digest, existing) for existing in digests):
                raise RuntimeError("Inbound and operator API keys must all differ")
            digests.append(digest)
            credentials.append((digest, principal))

    return tuple(inbound_credentials), tuple(credentials)


_INBOUND_CREDENTIALS, _OPERATORS = load_credentials()
_INBOUND_RATE_LIMIT = load_rate_limit(
    "AGENT_INBOUND_RATE_LIMIT_PER_MINUTE",
    DEFAULT_INBOUND_RATE_LIMIT_PER_MINUTE,
)
_OPERATOR_RATE_LIMIT = load_rate_limit(
    "AGENT_OPERATOR_RATE_LIMIT_PER_MINUTE",
    DEFAULT_OPERATOR_RATE_LIMIT_PER_MINUTE,
)
_INBOUND_LIMITER = RollingWindowRateLimiter(_INBOUND_RATE_LIMIT)
_OPERATOR_LIMITER = RollingWindowRateLimiter(_OPERATOR_RATE_LIMIT)


def _enforce_rate_limit(request, limiter, identity):
    retry_after = limiter.check(identity)
    if retry_after is None:
        return
    audit_denial(request, "rate_limit_exceeded", identity)
    raise HTTPException(
        status_code=429,
        detail="Rate limit exceeded",
        headers={"Retry-After": str(retry_after)},
    )


def _authenticate_inbound(request: Request, key: str | None) -> str:
    digest = _key_digest(key) if key else None
    source = None
    if digest is not None:
        for candidate_digest, candidate_source in _INBOUND_CREDENTIALS:
            if hmac.compare_digest(digest, candidate_digest):
                source = candidate_source

    if source is None:
        audit_denial(request, "invalid_inbound_credential")
        raise HTTPException(status_code=401, detail="Invalid API credentials")

    identity = f"channel:{source}"
    _enforce_rate_limit(request, _INBOUND_LIMITER, identity)
    return source


def require_inbound_key(
    request: Request, key: str | None = Depends(api_key_header)
) -> str:
    return _authenticate_inbound(request, key)


def require_inbound_channel(source: str):
    if not _valid_channel(source):
        raise ValueError(f"Invalid inbound channel: {source}")

    def authenticate(
        request: Request, key: str | None = Depends(api_key_header)
    ) -> str:
        authenticated_source = _authenticate_inbound(request, key)
        if authenticated_source != source:
            audit_denial(
                request,
                "inbound_channel_denied",
                f"channel:{authenticated_source}",
            )
            raise HTTPException(status_code=403, detail="Channel is not authorized")
        return authenticated_source

    return authenticate


def require_operator_permission(permission: str):
    if permission not in OPERATOR_PERMISSIONS:
        raise ValueError(f"Unknown operator permission: {permission}")

    def authenticate(
        request: Request, key: str | None = Depends(api_key_header)
    ) -> OperatorPrincipal:
        if not key:
            audit_denial(request, "missing_operator_credential")
            raise HTTPException(status_code=401, detail="Invalid API credentials")
        digest = _key_digest(key)
        operator = None
        for candidate_digest, candidate in _OPERATORS:
            if hmac.compare_digest(digest, candidate_digest):
                operator = candidate
        if operator is None:
            audit_denial(request, "invalid_operator_credential")
            raise HTTPException(status_code=401, detail="Invalid API credentials")
        if permission not in operator.permissions:
            audit_denial(request, "operator_permission_denied", operator.actor)
            raise HTTPException(status_code=403, detail="Operator permission denied")
        _enforce_rate_limit(request, _OPERATOR_LIMITER, operator.actor)
        return operator

    return authenticate
