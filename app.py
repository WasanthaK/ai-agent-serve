import json
import os
from typing import Optional
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from openai import OpenAI
from pydantic import BaseModel, Field

from db import (
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
from tools import ToolExecutionError, execute_tool
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


def analyze_quote_request(
    message,
    source="direct",
    customer_name=None,
):
    try:
        response = client.responses.create(
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
        return json.loads(response.output_text)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Request analysis is temporarily unavailable",
        ) from None


@app.get("/")
def health():
    return {
        "status": "running",
        "service": "agent-server",
        "version": "3.3.0",
    }


@app.get("/service-catalog")
def retrieve_service_catalog():
    return service_catalog.as_dict()


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
    source: str = Depends(require_inbound_key),
):
    if request.source != source:
        audit_denial(http_request, "source_mismatch", f"channel:{source}")
        raise HTTPException(status_code=403, detail="Source is not authorized")

    result = analyze_quote_request(
        message=request.message,
        source=source,
        customer_name=request.customer_name,
    )

    request_id = save_request(
        source,
        request.customer_name,
        request.message,
        result,
    )

    saved_request = get_request(request_id)

    return {
        "request_id": request_id,
        "source": source,
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
    )

    return {
        "request_id": request_id,
        "message": saved_message,
        "workflow_status": updated_request["status"],
        "analysis": result,
    }


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

    record_event(
        request_id=request_id,
        event_type="tool_started",
        actor=operator.actor,
        details={
            "tool": tool_name,
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
        },
    )

    return {
        "request_id": request_id,
        "status": request["status"],
        "result": result,
    }
