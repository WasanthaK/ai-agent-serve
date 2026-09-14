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
    save_request,
    update_request_status,
)


app = FastAPI(
    title="Mac Mini Agent Server",
    version="3.0.0",
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class AgentRequest(BaseModel):
    message: str


class QuoteWebhookRequest(BaseModel):
    source: str
    customer_name: Optional[str] = None
    message: str


class WorkflowDecision(BaseModel):
    actor: str = Field(default="human", min_length=1, max_length=100)
    reason: Optional[str] = Field(default=None, max_length=1000)


QUOTE_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string"
        },
        "category": {
            "type": "string"
        },
        "summary": {
            "type": "string"
        },
        "urgency": {
            "type": "string"
        },
        "next_action": {
            "type": "string"
        },
        "needs_human_review": {
            "type": "boolean"
        },
        "missing_information": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "follow_up_questions": {
            "type": "array",
            "items": {
                "type": "string"
            }
        }
    },
    "required": [
        "intent",
        "category",
        "summary",
        "urgency",
        "next_action",
        "needs_human_review",
        "missing_information",
        "follow_up_questions"
    ],
    "additionalProperties": False
}


def analyze_quote_request(
    message,
    source="direct",
    customer_name=None,
):
    response = client.responses.create(
        model="gpt-5.6",
        instructions="""
You are a quotation intake agent.

Analyse an incoming customer request and return structured information
for workflow automation.

Identify information that is genuinely required before a service
provider can meaningfully respond to the request. Do not demand every
possible detail. Only identify information whose absence prevents the
next practical step.

For each missing item, produce one short, customer-friendly follow-up
question. If no essential information is missing, return empty arrays
for missing_information and follow_up_questions.

Set needs_human_review to true for requests that are urgent, dangerous,
ambiguous, high-value, legally sensitive, or unusual. Otherwise set it
to false.

Do not claim that an appointment, price, availability, or service has
been confirmed.
""",
        input=f"""
Source: {source}
Customer: {customer_name or "Unknown"}
Message: {message}
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
        "version": "3.0.0",
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