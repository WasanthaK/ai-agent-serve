import json
import os
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from openai import OpenAI
from pydantic import BaseModel, Field

from db import (
    database_ready,
    get_request,
    get_request_events,
    get_request_messages,
    record_event,
    save_message,
    save_request,
    update_request_analysis,
    update_request_status,
)
from agent_skills import (
    DEFAULT_ANALYSIS_SKILLS,
    service_catalog,
    skill_registry,
)
from idempotency import (
    complete_webhook_delivery,
    hash_idempotency_key,
    hash_webhook_payload,
    release_webhook_delivery,
    reserve_webhook_delivery,
)
from inbound_adapters import normalize_website_message
from inbound_persistence import (
    InboundMessageConflictError,
    link_inbound_message_to_request,
    save_inbound_message,
)
from observability import (
    StructuredRequestLoggingMiddleware,
    correlation_exception_handler,
)
from operational_metrics import operational_metrics
from provider_selection import (
    ProviderSelectionConflictError,
    ProviderSelectionEligibilityError,
    ProviderSelectionNotFoundError,
    ProviderSelectionStateError,
    ProviderSelectionValidationError,
    get_provider_selection,
    select_providers_for_request,
)
from rfq_handoff import (
    RFQHandoffConflictError,
    RFQHandoffNotFoundError,
    RFQHandoffStateError,
    RFQHandoffValidationError,
    get_rfq_for_request,
    prepare_rfq_handoff,
)
from rfq_delivery import (
    RFQDeliveryConflictError,
    RFQDeliveryEligibilityError,
    RFQDeliveryNotFoundError,
    RFQDeliveryStateError,
    RFQDeliveryValidationError,
    authorize_rfq_delivery,
    confirm_rfq_delivery,
)
from rfq_response import (
    RFQResponseConflictError,
    RFQResponseNotFoundError,
    RFQResponseStateError,
    RFQResponseValidationError,
    ingest_rfq_response,
)
from tools import ToolExecutionError, execute_tool, get_tool_version
from security import (
    OperatorPrincipal,
    audit_denial,
    require_inbound_key,
    require_operator_permission,
)


app = FastAPI(
    title="Mac Mini Agent Server",
    version="3.3.0",
)
app.add_middleware(StructuredRequestLoggingMiddleware)
app.add_exception_handler(Exception, correlation_exception_handler)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class AgentRequest(BaseModel):
    message: str


class QuoteWebhookRequest(BaseModel):
    source: str
    customer_name: Optional[str] = None
    message: str


class WorkflowDecision(BaseModel):
    reason: Optional[str] = Field(
        default=None,
        max_length=1000,
    )


class ProviderSelectionDecision(BaseModel):
    service_slug: str = Field(
        min_length=1,
        max_length=120,
    )
    area_key: str = Field(
        min_length=1,
        max_length=120,
    )
    provider_ids: list[UUID]
    reason: Optional[str] = Field(
        default=None,
        max_length=1000,
    )


class RFQDeliveryConfirmation(BaseModel):
    response_deadline_at: datetime


class RFQProviderResponse(BaseModel):
    response_kind: str = Field(min_length=1, max_length=20)
    responded_at: datetime


class CustomerReply(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=5000,
    )
    channel: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )


QUOTE_ANALYSIS_SCHEMA = skill_registry.build_json_schema(
    DEFAULT_ANALYSIS_SKILLS
)

QUOTE_ANALYSIS_INSTRUCTIONS = skill_registry.build_instructions(
    DEFAULT_ANALYSIS_SKILLS
) + "\n\n" + service_catalog.build_analysis_instructions()

ANALYSIS_SKILL_VERSIONS = skill_registry.versions(
    DEFAULT_ANALYSIS_SKILLS
)


def analyze_quote_request(
    message,
    source="direct",
    customer_name=None,
):
    try:
        response = operational_metrics.measure_model_call(
            lambda: client.responses.create(
                model="gpt-5.6",
                instructions=QUOTE_ANALYSIS_INSTRUCTIONS,
                input=f"""
Source: {source}
Customer: {customer_name or "Unknown"}
Message or conversation:
{message}
""",
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "quote_request",
                        "strict": True,
                        "schema": QUOTE_ANALYSIS_SCHEMA,
                    }
                },
            )
        )
        return json.loads(response.output_text)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Request analysis is temporarily unavailable",
        ) from None


def _stored_analysis(saved_request):
    return {
        "intent": saved_request["intent"],
        "category": saved_request["category"],
        "summary": saved_request["summary"],
        "urgency": saved_request["urgency"],
        "next_action": saved_request["next_action"],
        "needs_human_review": saved_request["needs_human_review"],
        "missing_information": saved_request["missing_information"],
        "follow_up_questions": saved_request["follow_up_questions"],
    }


def _quote_webhook_response(saved_request):
    return {
        "request_id": saved_request["id"],
        "source": saved_request["source"],
        "customer_name": saved_request["customer_name"],
        "workflow_status": saved_request["status"],
        "analysis": _stored_analysis(saved_request),
    }


@app.get("/")
def health():
    return {
        "status": "running",
        "service": "agent-server",
        "version": "3.3.0",
    }


@app.get("/health/live")
def health_live():
    return {
        "status": "alive",
        "service": "agent-server",
    }


@app.get("/health/ready")
def health_ready():
    if not database_ready():
        raise HTTPException(
            status_code=503,
            detail="Service is not ready",
        )

    return {
        "status": "ready",
        "service": "agent-server",
        "dependencies": {
            "database": "ready",
        },
    }


@app.get("/service-catalog")
def retrieve_service_catalog():
    return service_catalog.as_dict()


@app.get(
    "/metrics/operational",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_operational_metrics():
    return operational_metrics.snapshot()


@app.post("/agent", dependencies=[Depends(require_operator_permission("analyze"))])
def run_agent(request: AgentRequest):
    return analyze_quote_request(
        message=request.message,
        source="direct",
    )


@app.post("/webhook/quote-request")
def quote_webhook(
    request: QuoteWebhookRequest,
    http_request: Request,
    idempotency_key: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key",
    ),
    source: str = Depends(require_inbound_key),
):
    if request.source != source:
        audit_denial(http_request, "source_mismatch", f"channel:{source}")
        raise HTTPException(status_code=403, detail="Source is not authorized")

    key_hash = None
    reserved_request_id = None

    if idempotency_key is not None:
        normalized_key = idempotency_key.strip()
        if not normalized_key or len(normalized_key) > 200:
            raise HTTPException(
                status_code=400,
                detail="Invalid Idempotency-Key",
            )
        key_hash = hash_idempotency_key(normalized_key)

    inbound_message = normalize_website_message(
        authenticated_channel=source,
        text=request.message,
        external_message_id=key_hash,
    )

    if key_hash is not None:
        payload_hash = hash_webhook_payload(
            inbound_message.channel,
            request.customer_name,
            inbound_message.text,
        )
        reservation = reserve_webhook_delivery(
            inbound_message.channel,
            key_hash,
            payload_hash,
        )
        reserved_request_id = reservation["request_id"]

        if reservation["action"] == "conflict":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Idempotency key was already used for a different request"
                ),
            )

        if reservation["action"] == "processing":
            raise HTTPException(
                status_code=409,
                detail="Request with this idempotency key is still processing",
                headers={"Retry-After": "2"},
            )

        if reservation["action"] == "completed":
            saved_request = get_request(reserved_request_id)
            if saved_request is None:
                raise HTTPException(
                    status_code=503,
                    detail="Stored idempotent request is temporarily unavailable",
                )
            try:
                persisted = save_inbound_message(inbound_message)
            except InboundMessageConflictError:
                raise HTTPException(
                    status_code=409,
                    detail="Conflicting website message identity",
                ) from None
            link_inbound_message_to_request(
                persisted["message"]["id"],
                reserved_request_id,
            )
            return _quote_webhook_response(saved_request)

    try:
        persisted = save_inbound_message(inbound_message)
    except InboundMessageConflictError:
        raise HTTPException(
            status_code=409,
            detail="Conflicting website message identity",
        ) from None

    try:
        result = analyze_quote_request(
            message=inbound_message.text,
            source=inbound_message.channel,
            customer_name=request.customer_name,
        )
    except Exception:
        if key_hash is not None:
            release_webhook_delivery(
                inbound_message.channel,
                key_hash,
                reserved_request_id,
            )
        raise

    try:
        request_id = save_request(
            inbound_message.channel,
            request.customer_name,
            inbound_message.text,
            result,
            request_id=reserved_request_id,
            skill_versions=ANALYSIS_SKILL_VERSIONS,
        )
    except Exception:
        if key_hash is not None:
            release_webhook_delivery(
                inbound_message.channel,
                key_hash,
                reserved_request_id,
            )
        raise

    saved_request = get_request(request_id)

    if key_hash is not None:
        complete_webhook_delivery(
            inbound_message.channel,
            key_hash,
            request_id,
        )

    link_inbound_message_to_request(
        persisted["message"]["id"],
        request_id,
    )

    return {
        "request_id": request_id,
        "source": inbound_message.channel,
        "customer_name": request.customer_name,
        "workflow_status": saved_request["status"],
        "analysis": result,
    }


@app.get("/requests/{request_id}", dependencies=[Depends(require_operator_permission("read"))])
def retrieve_request(request_id: UUID):
    request = get_request(request_id)

    if request is None:
        raise HTTPException(
            status_code=404,
            detail="Request not found",
        )

    return request


@app.get("/requests/{request_id}/events", dependencies=[Depends(require_operator_permission("read"))])
def retrieve_request_events(request_id: UUID):
    request = get_request(request_id)

    if request is None:
        raise HTTPException(
            status_code=404,
            detail="Request not found",
        )

    return {
        "request_id": request_id,
        "events": get_request_events(request_id),
    }


@app.get("/requests/{request_id}/messages", dependencies=[Depends(require_operator_permission("read"))])
def retrieve_request_messages(request_id: UUID):
    request = get_request(request_id)

    if request is None:
        raise HTTPException(
            status_code=404,
            detail="Request not found",
        )

    return {
        "request_id": request_id,
        "original_message": request["message"],
        "messages": get_request_messages(request_id),
    }


@app.post("/requests/{request_id}/reply")
def receive_customer_reply(
    request_id: UUID,
    reply: CustomerReply,
    operator: OperatorPrincipal = Depends(require_operator_permission("reply")),
):
    request = get_request(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")

    return _process_customer_reply(
        request_id, reply, request,
        channel=reply.channel or request["source"],
        actor=operator.actor,
    )


@app.post("/webhook/quote-request/{request_id}/reply")
def receive_channel_reply(
    request_id: UUID,
    reply: CustomerReply,
    http_request: Request,
    source: str = Depends(require_inbound_key),
):
    request = get_request(request_id)

    if request is None or request["source"] != source:
        audit_denial(http_request, "channel_request_denied", f"channel:{source}")
        raise HTTPException(status_code=404, detail="Request not found")

    if reply.channel is not None and reply.channel != source:
        audit_denial(http_request, "channel_mismatch", f"channel:{source}")
        raise HTTPException(status_code=403, detail="Channel is not authorized")

    return _process_customer_reply(
        request_id, reply, request, channel=source, actor=f"channel:{source}"
    )


def _process_customer_reply(request_id, reply, request, channel, actor):
    if request["status"] != "needs_information":
        raise HTTPException(
            status_code=409,
            detail=(
                "Customer replies can only be added while information "
                f"is required. Current status: {request['status']}"
            ),
        )

    saved_message = save_message(
        request_id=request_id,
        role="customer",
        channel=channel,
        message=reply.message,
        actor=actor,
    )

    messages = get_request_messages(request_id)

    conversation_lines = [
        f"Original customer request: {request['message']}"
    ]

    for message in messages:
        conversation_lines.append(
            f"{message['role'].title()} reply: {message['message']}"
        )

    conversation = "\n".join(conversation_lines)

    try:
        result = analyze_quote_request(
            message=conversation,
            source=request["source"],
            customer_name=request["customer_name"],
        )
    except Exception as exc:
        record_event(
            request_id=request_id,
            event_type="reanalysis_failed",
            actor="agent",
            details={
                "error_type": type(exc).__name__,
            },
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "The reply was saved, but the request could not "
                "be reanalysed."
            ),
        ) from exc

    updated_request = update_request_analysis(
        request_id=request_id,
        result=result,
        skill_versions=ANALYSIS_SKILL_VERSIONS,
    )

    return {
        "request_id": request_id,
        "message": saved_message,
        "workflow_status": updated_request["status"],
        "analysis": result,
    }


@app.get(
    "/requests/{request_id}/provider-selection",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_provider_selection(request_id: UUID):
    try:
        selection = get_provider_selection(request_id)
    except ProviderSelectionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if selection is None:
        raise HTTPException(
            status_code=404,
            detail="Provider selection not found",
        )

    return selection


@app.post("/requests/{request_id}/provider-selection")
def select_request_providers(
    request_id: UUID,
    decision: ProviderSelectionDecision,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return select_providers_for_request(
            request_id,
            decision.service_slug,
            decision.area_key,
            decision.provider_ids,
            actor=operator.actor,
            reason=decision.reason,
        )
    except ProviderSelectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProviderSelectionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        ProviderSelectionStateError,
        ProviderSelectionEligibilityError,
        ProviderSelectionConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/rfq-handoff",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_rfq_handoff(request_id: UUID):
    try:
        rfq = get_rfq_for_request(request_id)
    except RFQHandoffValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if rfq is None:
        raise HTTPException(status_code=404, detail="RFQ handoff not found")

    return rfq


@app.post("/requests/{request_id}/rfq-handoff")
def prepare_request_rfq_handoff(
    request_id: UUID,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return prepare_rfq_handoff(
            request_id,
            actor=operator.actor,
        )
    except RFQHandoffNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RFQHandoffValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        RFQHandoffStateError,
        RFQHandoffConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/requests/{request_id}/rfq-handoffs/{handoff_id}/authorize-delivery"
)
def authorize_request_rfq_delivery(
    request_id: UUID,
    handoff_id: UUID,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return authorize_rfq_delivery(
            request_id,
            handoff_id,
            actor=operator.actor,
        )
    except RFQDeliveryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RFQDeliveryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        RFQDeliveryStateError,
        RFQDeliveryEligibilityError,
        RFQDeliveryConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/requests/{request_id}/rfq-handoffs/{handoff_id}/confirm-delivery"
)
def confirm_request_rfq_delivery(
    request_id: UUID,
    handoff_id: UUID,
    confirmation: RFQDeliveryConfirmation,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return confirm_rfq_delivery(
            request_id,
            handoff_id,
            confirmation.response_deadline_at,
            actor=operator.actor,
        )
    except RFQDeliveryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RFQDeliveryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        RFQDeliveryStateError,
        RFQDeliveryEligibilityError,
        RFQDeliveryConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/requests/{request_id}/rfq-handoffs/{handoff_id}/provider-response"
)
def record_request_rfq_provider_response(
    request_id: UUID,
    handoff_id: UUID,
    response: RFQProviderResponse,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return ingest_rfq_response(
            request_id,
            handoff_id,
            response.response_kind,
            response.responded_at,
            actor=operator.actor,
        )
    except RFQResponseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RFQResponseValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        RFQResponseStateError,
        RFQResponseConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/requests/{request_id}/approve")
def approve_request(
    request_id: UUID,
    decision: WorkflowDecision,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    request = get_request(request_id)

    if request is None:
        raise HTTPException(
            status_code=404,
            detail="Request not found",
        )

    if request["status"] != "awaiting_human_review":
        raise HTTPException(
            status_code=409,
            detail=(
                "Only requests awaiting human review can be approved. "
                f"Current status: {request['status']}"
            ),
        )

    updated = update_request_status(
        request_id=request_id,
        new_status="approved",
        actor=operator.actor,
        event_type="request_approved",
        details={
            "reason": decision.reason,
        },
    )

    return updated


@app.post("/requests/{request_id}/reject")
def reject_request(
    request_id: UUID,
    decision: WorkflowDecision,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    request = get_request(request_id)

    if request is None:
        raise HTTPException(
            status_code=404,
            detail="Request not found",
        )

    rejectable_statuses = {
        "needs_information",
        "awaiting_human_review",
        "ready",
        "approved",
    }

    if request["status"] not in rejectable_statuses:
        raise HTTPException(
            status_code=409,
            detail=(
                "Request cannot be rejected from its current status: "
                f"{request['status']}"
            ),
        )

    updated = update_request_status(
        request_id=request_id,
        new_status="rejected",
        actor=operator.actor,
        event_type="request_rejected",
        details={
            "reason": decision.reason,
        },
    )

    return updated


@app.post("/requests/{request_id}/tools/{tool_name}")
def run_request_tool(
    request_id: UUID,
    tool_name: str,
    operator: OperatorPrincipal = Depends(require_operator_permission("tools")),
):
    request = get_request(request_id)

    if request is None:
        raise HTTPException(
            status_code=404,
            detail="Request not found",
        )

    allowed_tools_by_status = {
        "needs_information": {
            "prepare_customer_follow_up",
        },
    }

    allowed_tools = allowed_tools_by_status.get(
        request["status"],
        set(),
    )

    if tool_name not in allowed_tools:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Tool '{tool_name}' is not allowed when the "
                f"request status is '{request['status']}'."
            ),
        )

    tool_version = get_tool_version(tool_name)

    record_event(
        request_id=request_id,
        event_type="tool_started",
        actor=operator.actor,
        details={
            "tool": tool_name,
            "tool_version": tool_version,
        },
    )

    try:
        result = execute_tool(
            tool_name=tool_name,
            request=request,
        )
    except ToolExecutionError as exc:
        record_event(
            request_id=request_id,
            event_type="tool_failed",
            actor=operator.actor,
            details={
                "tool": tool_name,
                "tool_version": tool_version,
                "error_type": type(exc).__name__,
            },
        )

        raise HTTPException(
            status_code=422,
            detail="Tool could not be executed",
        ) from exc

    record_event(
        request_id=request_id,
        event_type="tool_completed",
        actor=operator.actor,
        details={
            "tool": tool_name,
            "tool_version": tool_version,
        },
    )

    return {
        "request_id": request_id,
        "status": request["status"],
        "result": result,
    }
