import os
import json
import uuid
import psycopg

from typing import Optional

from db import save_request

from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI(title="Mac Mini Agent Server")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class AgentRequest(BaseModel):
    message: str


class QuoteWebhookRequest(BaseModel):
    source: str
    customer_name: Optional[str] = None
    message: str

@app.get("/")
def health():
    return {
        "status": "running",
        "service": "agent-server"
    }


@app.post("/agent")
def run_agent(request: AgentRequest):
    response = client.responses.create(
        model="gpt-5.6",
        instructions="""
You are a quotation intake agent.

Analyze the customer's request and return structured information
that another system can use for workflow automation.

Set needs_human_review to true for urgent, dangerous, ambiguous,
high-value, or unusual requests. Otherwise set it to false.
""",
        input=request.message,
        text={
            "format": {
                "type": "json_schema",
                "name": "quote_request",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "intent": {"type": "string"},
                        "category": {"type": "string"},
                        "summary": {"type": "string"},
                        "urgency": {"type": "string"},
                        "next_action": {"type": "string"},
                        "needs_human_review": {"type": "boolean"}
                    },
                    "required": [
                        "intent",
                        "category",
                        "summary",
                        "urgency",
                        "next_action",
                        "needs_human_review"
                    ],
                    "additionalProperties": False
                }
            }
        }
    )

    return json.loads(response.output_text)


@app.post("/webhook/quote-request")
def quote_webhook(request: QuoteWebhookRequest):
    response = client.responses.create(
        model="gpt-5.6",
        instructions="""
You are a quotation intake agent.

Analyze the incoming customer request and return structured information
for workflow automation.

Set needs_human_review to true for urgent, dangerous, ambiguous,
high-value, or unusual requests. Otherwise set it to false.
""",
        input=f"""
Source: {request.source}
Customer: {request.customer_name or "Unknown"}
Message: {request.message}
""",
        text={
            "format": {
                "type": "json_schema",
                "name": "quote_request",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "intent": {"type": "string"},
                        "category": {"type": "string"},
                        "summary": {"type": "string"},
                        "urgency": {"type": "string"},
                        "next_action": {"type": "string"},
                        "needs_human_review": {"type": "boolean"}
                    },
                    "required": [
                        "intent",
                        "category",
                        "summary",
                        "urgency",
                        "next_action",
                        "needs_human_review"
                    ],
                    "additionalProperties": False
                }
            }
        }
    )

    result = json.loads(response.output_text)

    request_id = save_request(
        request.source,
        request.customer_name,
        request.message,
        result
    )

    return {
        "request_id": str(request_id),
        "source": request.source,
        "customer_name": request.customer_name,
        "analysis": result
    }


