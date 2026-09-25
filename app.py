import json
import os
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException
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
from agent_skills import DEFAULT_ANALYSIS_SKILLS, skill_registry
from tools import ToolExecutionError, execute_tool


app = FastAPI(
    title="Mac Mini Agent Server",
    version="3.1.0",
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class AgentRequest(BaseModel):
    message: str


class QuoteWebhookRequest(BaseModel):
    source: str
    customer_name: Optional[str] = None
    message: str


class WorkflowDecision(BaseModel):
    actor: str = Field(
        default="human",
        min_length=1,
        max_length=100,
    )
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
)


def analyze_quote_request(
    message,
    source="direct",
    customer_name=None,
):
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


@app.get("/")
def health():
    return {
        "status": "running",
        "service": "agent-server",
        "version": "3.1.0",
    }


@app.post("/agent")
def run_agent(request: AgentRequest):
    return analyze_quote_request(
        message=request.message,
        source="direct",
    )


@app.post("/webhook/quote-request")
def quote_webhook(request: QuoteWebhookRequest):
    result = analyze_quote_request(
        message=request.message,
        source=request.source,
        customer_name=request.customer_name,
    )

    request_id = save_request(
        request.source,
        request.customer_name,
        request.message,
        result,
    )

    saved_request = get_request(request_id)

    return {
        "request_id": request_id,
        "source": request.source,
        "customer_name": request.customer_name,
        "workflow_status": saved_request["status"],
        "analysis": result,
    }


@app.get("/requests/{request_id}")
def retrieve_request(request_id: UUID):
    request = get_request(request_id)

    if request is None:
        raise HTTPException(
            status_code=404,
            detail="Request not found",
        )

    return request


@app.get("/requests/{request_id}/events")
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


@app.get("/requests/{request_id}/messages")
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
):
    request = get_request(request_id)

    if request is None:
        raise HTTPException(
            status_code=404,
            detail="Request not found",
        )

    if request["status"] != "needs_information":
        raise HTTPException(
            status_code=409,
            detail=(
                "Customer replies can only be added while information "
                f"is required. Current status: {request['status']}"
            ),
        )

    channel = reply.channel or request["source"]

    saved_message = save_message(
        request_id=request_id,
        role="customer",
        channel=channel,
        message=reply.message,
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
        actor=decision.actor,
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
        actor=decision.actor,
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
        actor="agent",
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
            actor="agent",
            details={
                "tool": tool_name,
                "error": str(exc),
            },
        )

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    record_event(
        request_id=request_id,
        event_type="tool_completed",
        actor="agent",
        details={
            "tool": tool_name,
            "result": result,
        },
    )

    return {
        "request_id": request_id,
        "status": request["status"],
        "result": result,
    }