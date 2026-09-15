class ToolExecutionError(Exception):
    pass


def prepare_customer_follow_up(request):
    questions = request.get("follow_up_questions") or []

    if not questions:
        raise ToolExecutionError(
            "This request has no follow-up questions to prepare."
        )

    customer_name = request.get("customer_name")
    greeting = (
        f"Hi {customer_name},"
        if customer_name
        else "Hello,"
    )

    question_lines = "\n".join(
        f"{index}. {question}"
        for index, question in enumerate(questions, start=1)
    )

    message = (
        f"{greeting}\n\n"
        "Thank you for your quote request. "
        "To help us understand the job, could you please provide "
        "the following information?\n\n"
        f"{question_lines}\n\n"
        "Once we receive these details, we can continue processing "
        "your request."
    )

    return {
        "tool": "prepare_customer_follow_up",
        "delivery_status": "draft_only",
        "channel": request.get("source", "unknown"),
        "recipient": customer_name,
        "message": message,
    }


TOOL_REGISTRY = {
    "prepare_customer_follow_up": prepare_customer_follow_up,
}


def execute_tool(tool_name, request):
    tool = TOOL_REGISTRY.get(tool_name)

    if tool is None:
        raise ToolExecutionError(
            f"Tool is not registered: {tool_name}"
        )

    return tool(request)