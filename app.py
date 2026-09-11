import os
import json
import uuid
import psycopg

from typing import Optional

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

def save_request(source, customer_name, message, result):
    request_id = uuid.uuid4()

    with psycopg.connect(
    	host=os.getenv("POSTGRES_HOST"),
    	port=os.getenv("POSTGRES_PORT"),
    	dbname=os.getenv("POSTGRES_DB"),
    	user=os.getenv("POSTGRES_USER"),
    	password=os.getenv("POSTGRES_PASSWORD")
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_requests (
                    id,
                    source,
                    customer_name,
                    message,
                    intent,
                    category,
                    summary,
                    urgency,
                    next_action,
                    needs_human_review,
                    status
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    request_id,
                    source,
                    customer_name,
                    message,
                    result["intent"],
                    result["category"],
                    result["summary"],
                    result["urgency"],
                    result["next_action"],
                    result["needs_human_review"],
                    "awaiting_human_review"
                    if result["needs_human_review"]
                    else "ready"
                )
            )

    return request_id

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


