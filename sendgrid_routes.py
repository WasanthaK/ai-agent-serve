"""FastAPI route registration for verified SendGrid inbound email."""

import os
from typing import Callable

from fastapi import APIRouter, Header, HTTPException, Request
from psycopg.errors import UniqueViolation
from pydantic import ValidationError

from inbound_adapters import normalize_email_message
from inbound_persistence import (
    InboundMessageConflictError,
    link_inbound_message_to_request,
    save_inbound_message,
)
from security import audit_denial
from sendgrid_inbound import (
    SENDGRID_SIGNATURE_HEADER,
    SENDGRID_TIMESTAMP_HEADER,
    SendGridConfigurationError,
    SendGridPayloadError,
    build_sendgrid_email_envelope,
    verify_sendgrid_signature,
)


def build_sendgrid_router(
    *,
    analyze_quote_request: Callable,
    save_request: Callable,
    get_request: Callable,
    skill_versions,
) -> APIRouter:
    router = APIRouter()

    @router.post("/webhook/sendgrid/inbound")
    async def receive_sendgrid_inbound(
        http_request: Request,
        signature: str | None = Header(
            default=None,
            alias=SENDGRID_SIGNATURE_HEADER,
        ),
        timestamp: str | None = Header(
            default=None,
            alias=SENDGRID_TIMESTAMP_HEADER,
        ),
    ):
        raw_body = await http_request.body()
        public_key = os.getenv("SENDGRID_INBOUND_PUBLIC_KEY", "")

        try:
            verified = verify_sendgrid_signature(
                raw_body=raw_body,
                signature=signature,
                timestamp=timestamp,
                public_key_b64=public_key,
            )
        except SendGridConfigurationError:
            raise HTTPException(
                status_code=503,
                detail="SendGrid inbound verification is not configured",
            ) from None

        if not verified:
            audit_denial(
                http_request,
                "invalid_sendgrid_signature",
                "provider:sendgrid",
            )
            raise HTTPException(
                status_code=401,
                detail="Invalid SendGrid webhook signature",
            )

        try:
            form = await http_request.form()
            envelope = build_sendgrid_email_envelope(form)
            normalized = normalize_email_message(
                authenticated_channel="email",
                envelope=envelope,
            )
        except (SendGridPayloadError, ValidationError, ValueError):
            raise HTTPException(
                status_code=422,
                detail="Invalid SendGrid inbound email payload",
            ) from None

        try:
            persisted = save_inbound_message(normalized)
        except InboundMessageConflictError:
            raise HTTPException(
                status_code=409,
                detail="Conflicting SendGrid message identity",
            ) from None

        inbound_record = persisted["message"]
        inbound_id = inbound_record["id"]
        linked_request_id = inbound_record["linked_request_id"]

        if linked_request_id is not None:
            saved_request = get_request(linked_request_id)
            if saved_request is None:
                raise HTTPException(
                    status_code=503,
                    detail="Linked request is temporarily unavailable",
                )
            return {
                "status": "accepted",
                "request_id": linked_request_id,
                "workflow_status": saved_request["status"],
            }

        # The inbound UUID is also the deterministic request UUID. If a prior
        # delivery completed request creation but failed before linkage/response,
        # the retry recovers the same request without a second model call.
        request_id = inbound_id
        saved_request = get_request(request_id)
        if saved_request is not None:
            link_inbound_message_to_request(inbound_id, request_id)
            return {
                "status": "accepted",
                "request_id": request_id,
                "workflow_status": saved_request["status"],
            }

        sender = normalized.sender
        customer_name = None
        if sender is not None:
            customer_name = sender.display_name or sender.address

        result = analyze_quote_request(
            message=normalized.text,
            source=normalized.channel,
            customer_name=customer_name,
        )

        try:
            save_request(
                normalized.channel,
                customer_name,
                normalized.text,
                result,
                request_id=request_id,
                skill_versions=(
                    skill_versions(result)
                    if callable(skill_versions)
                    else skill_versions
                ),
            )
        except UniqueViolation:
            # Concurrent retry: both deliveries intentionally use the same
            # deterministic request UUID. Only the first insert wins.
            pass

        saved_request = get_request(request_id)
        if saved_request is None:
            raise HTTPException(
                status_code=503,
                detail="Inbound request is temporarily unavailable",
            )

        link_inbound_message_to_request(inbound_id, request_id)

        return {
            "status": "accepted",
            "request_id": request_id,
            "workflow_status": saved_request["status"],
        }

    return router
