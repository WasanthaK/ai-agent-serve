from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ProductSurface = Literal[
    "requestquote",
    "marketplace",
    "sendquote",
    "widget",
    "connector",
]

RequirementChannel = Literal[
    "web",
    "email",
    "whatsapp",
    "marketplace",
    "voice",
    "messenger",
    "api",
]

ParticipantRole = Literal[
    "customer",
    "provider",
    "buyer",
    "operator",
    "system",
]

EvidenceKind = Literal[
    "supplied_fact",
    "authoritative_platform_fact",
    "expert_inference",
    "assumption",
    "estimate",
    "unknown",
    "safety_critical_uncertainty",
]

InteractionDirective = Literal[
    "ask_clarification",
    "ready_for_pricing",
    "needs_human_review",
    "inspection_required",
    "safety_escalation",
]


class RequirementMediaReference(BaseModel):
    """Reference to media owned by the calling product or connector."""

    model_config = ConfigDict(extra="forbid")

    reference: str = Field(min_length=1, max_length=1000)
    media_type: str = Field(min_length=1, max_length=200)
    kind: Literal[
        "image",
        "audio",
        "video",
        "document",
        "transcript",
        "other",
    ] = "other"
    filename: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
    )


class RequirementTurnMessage(BaseModel):
    """Normalized message content for one expert conversation turn."""

    model_config = ConfigDict(extra="forbid")

    external_message_id: str = Field(min_length=1, max_length=500)
    external_thread_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    text: str = Field(min_length=1, max_length=20000)
    media: list[RequirementMediaReference] = Field(
        default_factory=list,
        max_length=20,
    )


class AgentExecutionContext(BaseModel):
    """Explicit Quixo/product acting context; no authority is inferred."""

    model_config = ConfigDict(extra="forbid")

    participant_role: ParticipantRole
    provider_company_id: Optional[UUID] = None
    buyer_organization_id: Optional[UUID] = None
    identity_user_id: Optional[UUID] = None
    public_reference: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
    )


class RequirementBusinessReferences(BaseModel):
    """Stable references to records owned by Quixo products."""

    model_config = ConfigDict(extra="forbid")

    service_request_id: Optional[UUID] = None
    quotation_id: Optional[UUID] = None


class PriorExpertState(BaseModel):
    """Reference to a prior expert package when continuing a conversation."""

    model_config = ConfigDict(extra="forbid")

    package_id: UUID
    package_version: int = Field(ge=1)


class RequirementConversationTurn(BaseModel):
    """Channel-neutral input contract for conversational requirement intelligence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    product_surface: ProductSurface
    channel: RequirementChannel
    correlation_id: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=500)
    message: RequirementTurnMessage
    actor_context: AgentExecutionContext
    business_references: RequirementBusinessReferences = Field(
        default_factory=RequirementBusinessReferences
    )
    prior_expert_state: Optional[PriorExpertState] = None
    locale: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=35,
    )
    timezone: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )


class RequirementEvidence(BaseModel):
    """Evidence item preserving fact/inference/assumption semantics."""

    model_config = ConfigDict(extra="forbid")

    kind: EvidenceKind
    statement: str = Field(min_length=1, max_length=4000)
    source_reference: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=1000,
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )


class RequirementWorkPackage(BaseModel):
    """A non-priced unit of work inferred or supplied for the requirement."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    description: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=4000,
    )


class InspectionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "not_required",
        "recommended",
        "required",
        "unknown",
    ]
    reason: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=2000,
    )


class RequirementIntelligencePackage(BaseModel):
    """Price-neutral expert interpretation of a service requirement."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    package_id: UUID
    package_version: int = Field(ge=1)
    domain: str = Field(min_length=1, max_length=200)
    subdomain: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    customer_objective: str = Field(min_length=1, max_length=4000)
    interpreted_scope: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    work_packages: list[RequirementWorkPackage] = Field(
        default_factory=list,
        max_length=100,
    )
    materials_equipment_concepts: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    labour_concepts: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    known_quantities: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    missing_information: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    clarification_questions: list[str] = Field(
        default_factory=list,
        max_length=50,
    )
    assumptions: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    exclusions: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    safety_compliance: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    inspection: InspectionAssessment
    environmental_context_constraints: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    dependencies: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    ready_for_pricing: bool
    confidence_by_section: dict[str, float] = Field(default_factory=dict)
    evidence: list[RequirementEvidence] = Field(
        default_factory=list,
        max_length=200,
    )


class ExpertProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: UUID
    model: str = Field(min_length=1, max_length=200)
    skill_versions: dict[str, str] = Field(default_factory=dict)


class RequirementConversationTurnResponse(BaseModel):
    """Expert response contract. Content only; it carries no send authority."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    requirement_package: RequirementIntelligencePackage
    directive: InteractionDirective
    clarification_questions: list[str] = Field(
        default_factory=list,
        max_length=50,
    )
    reply_draft: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=10000,
    )
    requires_human_review: bool = False
    safety_escalated: bool = False
    provenance: ExpertProvenance


class ExpertRequirementTurnRequest(BaseModel):
    """Stateless API envelope for one requirement-intelligence turn."""

    model_config = ConfigDict(extra="forbid")

    turn: RequirementConversationTurn
    prior_requirement_package: Optional[RequirementIntelligencePackage] = None
