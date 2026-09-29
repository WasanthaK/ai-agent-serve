"""FastAPI route registration for verified Twilio WhatsApp inbound messages."""

import os
from typing import Callable

from fastapi import APIRouter, Header, HTTPException, Request
from psycopg.errors import UniqueViolation
from pydantic import ValidationError

from inbound_adapters import normalize_whatsapp_message
from inbound_persistence import (
    InboundMessageConflictError,
    link_inbound_message_to_request,
    save_inbound_message,
)
from security import audit_denial
from twilio_whatsapp import (
    TWILIO_SIGNATURE_HEADER,
    TwilioConfigurationError,
    TwilioWhatsAppPayloadError,
    build_twilio_whatsapp_envelope,
    validate_public_webhook_url,
    verify_twilio_signature,
)


def build_twilio_whatsapp_router(
    *,
    analyze_quote_request: Callable,
    save_request: Callable,
    get_request: Callable,
    skill_versions,
) -> APIRouter:
    router = APIRouter()

    @router.post("/webhook/twilio/whatsapp")
    async def receive_twilio_whatsapp(
        http_request: Request,
        signature: str | None = Header(
            default=None,
            alias=TWILIO_SIGNATURE_HEADER,
        ),
    ):
        auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        expected_sender = os.getenv("TWILIO_WHATSAPP_SENDER", "")
        expected_service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID", "")
        configured_webhook_url = os.getenv("TWILIO_WHATSAPP_WEBHOOK_URL", "")

        try:
            webhook_url = validate_public_webhook_url(configured_webhook_url)
        except TwilioConfigurationError:
            raise HTTPException(
                status_code=503,
                detail="Twilio WhatsApp webhook verification is not configured",
            ) from None

        form = await http_request.form()
        form_params = {key: str(value) for key, value in form.items()}

        try:
            verified = verify_twilio_signature(
                webhook_url=webhook_url,
                form_params=form_params,
                signature=signature,
                auth_token=auth_token,
            )
        except TwilioConfigurationError:
            raise HTTPException(
                status_code=503,
                detail="Twilio WhatsApp webhook verification is not configured",
            ) from None

        if not verified:
            audit_denial(
                http_request,
                "invalid_twilio_signature",
                "provider:twilio-whatsapp",
            )
            raise HTTPException(
                status_code=401,
                detail="Invalid Twilio webhook signature",
            )

        try:
            envelope = build_twilio_whatsapp_envelope(
                form,
                expected_account_sid=account_sid,
                expected_sender=expected_sender,
                expected_messaging_service_sid=expected_service_sid or None,
            )
            normalized = normalize_whatsapp_message(
                authenticated_channel="whatsapp",
                envelope=envelope,
            )
        except (TwilioConfigurationError, TwilioWhatsAppPayloadError, ValidationError, ValueError):
            raise HTTPException(
                status_code=422,
                detail="Invalid Twilio WhatsApp payload",
            ) from None

        try:
            persisted = save_inbound_message(normalized)
        except InboundMessageConflictError:
            raise HTTPException(
                status_code=409,
                detail="Conflicting Twilio WhatsApp message identity",
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
            customer_name = sender.display_name or sender.address or sender.external_id

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
                skill_versions=skill_versions,
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
