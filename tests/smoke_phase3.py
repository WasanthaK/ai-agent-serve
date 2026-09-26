import json
import os
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE_URL = os.getenv(
    "AGENT_BASE_URL",
    "http://localhost:8000",
).rstrip("/")
INBOUND_SOURCE = os.getenv("AGENT_INBOUND_SOURCE", "website")


def api_key_for(path):
    if path in ("/", "/service-catalog"):
        return None
    name = "AGENT_INBOUND_API_KEY" if path.startswith("/webhook/quote-request") else "AGENT_OPERATOR_API_KEY"
    key = os.getenv(name)
    if not key:
        raise RuntimeError(f"Set {name} before running the smoke test")
    return key


def api_request(method, path, body=None):
    data = None
    headers = {}
    key = api_key_for(path)
    if key:
        headers["X-API-Key"] = key

    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        f"{BASE_URL}{path}",
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=120) as response:
            payload = response.read().decode("utf-8")
            return response.status, json.loads(payload)
    except HTTPError as exc:
        payload = exc.read().decode("utf-8")
        return exc.code, json.loads(payload)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def pass_step(message):
    print(f"PASS: {message}")


def main():
    status, health = api_request("GET", "/")

    require(status == 200, "Health endpoint did not return 200")
    require(
        health.get("version") == "3.3.0",
        "Unexpected API version",
    )
    pass_step("service health and version")

    status, incomplete = api_request(
        "POST",
        "/webhook/quote-request",
        {
            "source": INBOUND_SOURCE,
            "customer_name": "Phase 3 Smoke Test",
            "message": "I need a plumber.",
        },
    )

    require(status == 200, "Could not create incomplete request")
    require(
        incomplete["workflow_status"] == "needs_information",
        "Incomplete request did not enter needs_information",
    )
    require(
        incomplete["analysis"]["missing_information"],
        "Missing-information list is empty",
    )
    require(
        incomplete["analysis"]["follow_up_questions"],
        "Follow-up question list is empty",
    )

    incomplete_id = incomplete["request_id"]
    pass_step("missing-information workflow")

    status, tool_result = api_request(
        "POST",
        (
            f"/requests/{incomplete_id}"
            "/tools/prepare_customer_follow_up"
        ),
    )

    require(status == 200, "Follow-up tool did not execute")
    require(
        tool_result["result"]["delivery_status"] == "draft_only",
        "Follow-up tool was not restricted to draft_only",
    )
    require(
        tool_result["result"]["message"],
        "Follow-up draft is empty",
    )
    pass_step("controlled follow-up tool")

    status, reply_result = api_request(
        "POST",
        f"/webhook/quote-request/{incomplete_id}/reply",
        {
            "message": (
                "The kitchen tap is dripping continuously from the "
                "spout, but there is no flooding, gas smell or "
                "electrical danger. The property is 25 Test Street, "
                "Brisbane QLD 4000. Weekdays after 2 PM are suitable. "
                "My test contact number is 0400 000 000."
            )
        },
    )

    require(status == 200, "Customer reply was not accepted")
    require(
        reply_result["workflow_status"] == "ready",
        (
            "Completed request did not become ready. "
            f"Actual status: {reply_result['workflow_status']}"
        ),
    )
    require(
        not reply_result["analysis"]["missing_information"],
        "Missing information remained after complete reply",
    )
    pass_step("customer reply and conversational reanalysis")

    status, duplicate_reply = api_request(
        "POST",
        f"/webhook/quote-request/{incomplete_id}/reply",
        {
            "message": "This duplicate reply must be rejected."
        },
    )

    require(status == 409, "Duplicate reply did not return 409")
    pass_step("invalid reply transition blocked")

    status, messages = api_request(
        "GET",
        f"/requests/{incomplete_id}/messages",
    )

    require(status == 200, "Could not retrieve messages")
    require(
        len(messages["messages"]) == 1,
        "Unexpected number of stored customer messages",
    )
    pass_step("persistent conversation history")

    status, events = api_request(
        "GET",
        f"/requests/{incomplete_id}/events",
    )

    require(status == 200, "Could not retrieve events")

    event_types = {
        event["event_type"]
        for event in events["events"]
    }

    required_events = {
        "request_created",
        "tool_started",
        "tool_completed",
        "customer_message_received",
        "request_reanalysed",
    }

    require(
        required_events.issubset(event_types),
        f"Missing audit events: {required_events - event_types}",
    )
    pass_step("workflow and tool audit trail")

    status, safety_request = api_request(
        "POST",
        "/webhook/quote-request",
        {
            "source": INBOUND_SOURCE,
            "customer_name": "Safety Workflow Test",
            "message": (
                "There is a strong gas smell beside the kitchen stove "
                "at 25 Test Street, Brisbane QLD 4000. Everyone has "
                "left the property. The test contact number is "
                "0400 000 000."
            ),
        },
    )

    require(status == 200, "Could not create safety request")
    require(
        safety_request["workflow_status"]
        == "awaiting_human_review",
        "Safety request did not enter human review",
    )

    safety_id = safety_request["request_id"]
    pass_step("safety escalation")

    status, approval = api_request(
        "POST",
        f"/requests/{safety_id}/approve",
        {
            "reason": "Automated human-review workflow test",
        },
    )

    require(status == 200, "Approval endpoint failed")
    require(
        approval["status"] == "approved",
        "Approved request has incorrect status",
    )
    require(
        approval["approved_at"] is not None,
        "Approval timestamp was not stored",
    )
    pass_step("human approval workflow")

    status, repeated_approval = api_request(
        "POST",
        f"/requests/{safety_id}/approve",
        {
            "reason": "Duplicate approval must fail",
        },
    )

    require(
        status == 409,
        "Repeated approval did not return 409",
    )
    pass_step("invalid approval transition blocked")

    print()
    print("Phase 3 smoke test completed successfully.")
    print(f"Incomplete-flow request: {incomplete_id}")
    print(f"Safety-flow request: {safety_id}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
