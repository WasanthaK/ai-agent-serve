"""Trusted Quixo Messaging -> agent WhatsApp ingress."""

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.errors import UniqueViolation

from inbound_adapters import WhatsAppInboundEnvelope, normalize_whatsapp_message
from inbound_persistence import (
    InboundMessageConflictError,
    link_inbound_message_to_request,
    save_inbound_message,
)
from security import require_inbound_channel
from tenant_scope import TenantScopeError, tenant_id_from_request


def build_quixo_whatsapp_router(
    *,
    analyze_quote_request: Callable,
    save_request: Callable,
    get_request: Callable,
    skill_versions,
    channel_dependency=None,
) -> APIRouter:
    """Build the private WhatsApp ingress used by Quixo Messaging.

    The upstream Quixo messaging service remains responsible for the public
    Twilio webhook and Twilio signature verification. This route trusts only a
    credential explicitly bound to the `whatsapp` channel.
    """

    router = APIRouter()
    authenticate_whatsapp = channel_dependency or require_inbound_channel("whatsapp")

    @router.post("/webhook/whatsapp/inbound")
    def receive_quixo_whatsapp(
        envelope: WhatsAppInboundEnvelope,
        http_request: Request,
        authenticated_channel: str = Depends(authenticate_whatsapp),
    ):
        try:
            tenant_id = tenant_id_from_request(http_request)
        except TenantScopeError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        normalized = normalize_whatsapp_message(
            authenticated_channel=authenticated_channel,
            envelope=envelope,
        )

        try:
            persisted = (
                save_inbound_message(normalized)
                if tenant_id is None
                else save_inbound_message(
                    normalized,
                    tenant_id=tenant_id,
                )
            )
        except InboundMessageConflictError:
            raise HTTPException(
                status_code=409,
                detail="Conflicting WhatsApp message identity",
            ) from None

        inbound_record = persisted["message"]
        inbound_id = inbound_record["id"]
        linked_request_id = inbound_record["linked_request_id"]

        if linked_request_id is not None:
            saved_request = get_request(
                linked_request_id,
                tenant_id=tenant_id,
            )
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

        # Reuse the durable inbound UUID as the internal request UUID. This makes
        # retries recover the same request without creating duplicate work.
        request_id = inbound_id
        saved_request = get_request(
            request_id,
            tenant_id=tenant_id,
        )
        if saved_request is not None:
            if tenant_id is None:
                if tenant_id is None:
            link_inbound_message_to_request(inbound_id, request_id)
        else:
            link_inbound_message_to_request(
                inbound_id,
                request_id,
                tenant_id=tenant_id,
            )
            else:
                link_inbound_message_to_request(
                    inbound_id,
                    request_id,
                    tenant_id=tenant_id,
                )
            return {
                "status": "accepted",
                "request_id": request_id,
                "workflow_status": saved_request["status"],
            }

        sender = normalized.sender
        customer_name = None
        if sender is not None:
            customer_name = (
                sender.display_name
                or sender.address
                or sender.external_id
            )

        result = analyze_quote_request(
            message=normalized.text,
            source=normalized.channel,
            customer_name=customer_name,
        )

        try:
            if tenant_id is None:
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
            else:
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
                    tenant_id=tenant_id,
                )
        except UniqueViolation:
            # Concurrent retries intentionally converge on the same UUID.
            pass

        saved_request = get_request(
            request_id,
            tenant_id=tenant_id,
        )
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
