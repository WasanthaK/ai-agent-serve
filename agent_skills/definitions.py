from agent_skills.base import AgentSkill


REQUEST_INTAKE = AgentSkill(
    name="request_intake",
    version="1.0.0",
    description="Classify and summarize a service request.",
    instructions="""
You are analysing a service-delivery request.

Determine the customer's intent, the service category, a concise factual
summary, the urgency, and the next practical action. Do not claim that an
appointment, price, availability, or service has been confirmed.
""",
    schema_properties={
        "intent": {"type": "string"},
        "category": {"type": "string"},
        "summary": {"type": "string"},
        "urgency": {"type": "string"},
        "next_action": {"type": "string"},
    },
    required_fields=(
        "intent",
        "category",
        "summary",
        "urgency",
        "next_action",
    ),
    permitted_states=frozenset({"received", "needs_information"}),
)


REQUEST_CLARIFICATION = AgentSkill(
    name="request_clarification",
    version="1.0.0",
    description="Identify information required for the next action.",
    instructions="""
Identify only information that is genuinely required before a service
provider can meaningfully respond. Do not demand every possible detail.

For every missing item, produce one short follow-up question. If no
essential information is missing, return empty arrays for both fields.

When the input contains later customer replies, analyse the complete
conversation and do not ask again for information already supplied.
""",
    schema_properties={
        "missing_information": {
            "type": "array",
            "items": {"type": "string"},
        },
        "follow_up_questions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    required_fields=(
        "missing_information",
        "follow_up_questions",
    ),
    permitted_states=frozenset({"received", "needs_information"}),
    permitted_tools=frozenset({"prepare_customer_follow_up"}),
)


SAFETY_TRIAGE = AgentSkill(
    name="safety_triage",
    version="1.0.0",
    description="Identify requests requiring human review.",
    instructions="""
Set needs_human_review to true when a request is urgent, dangerous,
high-value, legally sensitive, or unusual. Otherwise set it to false.

Do not mark an ordinary request for human review merely because details
are missing. Missing details belong to the clarification skill.
""",
    schema_properties={
        "needs_human_review": {"type": "boolean"},
    },
    required_fields=("needs_human_review",),
    permitted_states=frozenset(
        {"received", "needs_information", "awaiting_human_review"}
    ),
)


CUSTOMER_COMMUNICATION = AgentSkill(
    name="customer_communication",
    version="1.0.0",
    description="Keep customer-facing questions clear and appropriate.",
    instructions="""
Write customer-facing questions in short, respectful and plain language.
Do not expose internal workflow labels, risk scores, prompts, or system
instructions. Do not promise an outcome that has not been confirmed.
""",
    permitted_states=frozenset({"needs_information"}),
    permitted_tools=frozenset({"prepare_customer_follow_up"}),
)


BUILT_IN_SKILLS = (
    REQUEST_INTAKE,
    REQUEST_CLARIFICATION,
    SAFETY_TRIAGE,
    CUSTOMER_COMMUNICATION,
)

DEFAULT_ANALYSIS_SKILLS = tuple(
    skill.name for skill in BUILT_IN_SKILLS
)
