import json
import os
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE_URL = os.getenv(
    "AGENT_BASE_URL",
    "http://localhost:8000",
).rstrip("/")


def api_request(method, path, body=None):
    data = None
    headers = {}
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
            return response.status, json.loads(
                response.read().decode("utf-8")
            )
    except HTTPError as exc:
        return exc.code, json.loads(
            exc.read().decode("utf-8")
        )


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def pass_step(message):
    print(f"PASS: {message}")


def main():
    status, health = api_request("GET", "/")
    require(status == 200, "Health endpoint did not return 200")
    require(health.get("version") == "3.2.0", "Unexpected API version")
    pass_step("service health and Phase 4 version")

    status, catalog = api_request("GET", "/service-catalog")
    require(status == 200, "Service catalogue did not return 200")
    require(len(catalog.get("groups", [])) == 7, "Expected seven groups")
    require(len(catalog.get("services", [])) == 47, "Expected 47 services")

    group_slugs = {group["slug"] for group in catalog["groups"]}
    service_slugs = {service["slug"] for service in catalog["services"]}
    require("trades" in group_slugs, "Trades group is missing")
    require("plumbing" in service_slugs, "Plumbing skill is missing")
    require("trades" not in service_slugs, "Group header is selectable")
    require(
        all(not group["selectable"] for group in catalog["groups"]),
        "A group header is selectable",
    )
    pass_step("service catalogue integrity")

    status, plumbing = api_request(
        "POST",
        "/webhook/quote-request",
        {
            "source": "phase4-smoke-test",
            "customer_name": "Plumbing Skill Test",
            "message": "My kitchen sink is leaking.",
        },
    )
    require(status == 200, "Plumbing request failed")
    require(
        plumbing["analysis"]["category"] == "plumbing",
        "Request was not classified as plumbing",
    )
    require(
        plumbing["workflow_status"] == "needs_information",
        "Incomplete plumbing request did not require information",
    )
    require(
        plumbing["analysis"]["follow_up_questions"],
        "Plumbing follow-up questions are empty",
    )
    require(
        not plumbing["analysis"]["needs_human_review"],
        "Ordinary plumbing request was unnecessarily escalated",
    )
    pass_step("plumbing classification and clarification")

    status, electrical = api_request(
        "POST",
        "/webhook/quote-request",
        {
            "source": "phase4-smoke-test",
            "customer_name": "Electrical Safety Test",
            "message": (
                "There are sparks coming from exposed wires beside the "
                "switchboard at 25 Test Street, Brisbane. The power is "
                "still on."
            ),
        },
    )
    require(status == 200, "Electrical request failed")
    require(
        electrical["analysis"]["category"] == "electrical",
        "Request was not classified as electrical",
    )
    require(
        electrical["analysis"]["needs_human_review"],
        "Dangerous electrical request was not escalated",
    )
    require(
        electrical["workflow_status"] == "awaiting_human_review",
        "Electrical request did not enter human review",
    )
    require(
        not electrical["analysis"]["follow_up_questions"],
        "Safety escalation was blocked by follow-up questions",
    )
    pass_step("electrical safety escalation")

    print()
    print("Phase 4 skill smoke test completed successfully.")
    print(f"Plumbing request: {plumbing['request_id']}")
    print(f"Electrical request: {electrical['request_id']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
