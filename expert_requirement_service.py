import json
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_skills import service_catalog, skill_registry
from expert_contracts import (
    ExpertProvenance,
    InspectionAssessment,
    RequirementConversationTurn,
    RequirementConversationTurnResponse,
    RequirementEvidence,
    RequirementIntelligencePackage,
    RequirementWorkPackage,
)
from operational_metrics import operational_metrics


REQUIREMENT_INTELLIGENCE_SKILLS = ("requirement_intelligence",)
DEFAULT_REQUIREMENT_MODEL = "gpt-5.6"


class RequirementReasoningError(Exception):
    """Base error for requirement-intelligence execution."""


class RequirementReasoningUnavailableError(RequirementReasoningError):
    """The model provider or structured response was unavailable."""


class RequirementReasoningValidationError(RequirementReasoningError):
    """The model response violated deterministic expert-contract rules."""


class PriorExpertStateError(RequirementReasoningError):
    """A continuation turn did not have the exact prior expert package."""


class _ModelWorkPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    description: str | None


class _ModelInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    reason: str | None


class _ModelEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    statement: str = Field(min_length=1, max_length=4000)
    source_reference: str | None
    confidence: float | None


class _ModelSectionConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: str = Field(min_length=1, max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)


class _RequirementModelOutput(BaseModel):
    """Provider-facing schema; identifiers and directives stay application-owned."""

    model_config = ConfigDict(extra="forbid")

    domain: str = Field(min_length=1, max_length=200)
    subdomain: str | None
    customer_objective: str = Field(min_length=1, max_length=4000)
    interpreted_scope: list[str]
    work_packages: list[_ModelWorkPackage]
    materials_equipment_concepts: list[str]
    labour_concepts: list[str]
    known_quantities: list[str]
    missing_information: list[str]
    clarification_questions: list[str]
    assumptions: list[str]
    exclusions: list[str]
    safety_compliance: list[str]
    inspection: _ModelInspection
    environmental_context_constraints: list[str]
    dependencies: list[str]
    ready_for_pricing: bool
    confidence_sections: list[_ModelSectionConfidence]
    evidence: list[_ModelEvidence]


def _strict_json_schema():
    schema = _RequirementModelOutput.model_json_schema()

    def normalize(node):
        if isinstance(node, dict):
            node.pop("title", None)
            node.pop("default", None)

            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
                node["additionalProperties"] = False

            for value in node.values():
                normalize(value)
        elif isinstance(node, list):
            for item in node:
                normalize(item)

    normalize(schema)
    return schema


def _model_instructions():
    skill = skill_registry.get("requirement_intelligence")
    return (
        f"## Skill: {skill.name} v{skill.version}\n"
        f"{skill.instructions.strip()}\n\n"
        f"{service_catalog.build_analysis_instructions()}\n\n"
        "Return only the structured requirement interpretation requested by the schema. "
        "All array items must be concise factual or clearly-labelled expert statements. "
        "Use evidence kind only from: supplied_fact, authoritative_platform_fact, "
        "expert_inference, assumption, estimate, unknown, safety_critical_uncertainty. "
        "Use inspection status only from: not_required, recommended, required, unknown. "
        "If a dangerous condition or safety-critical uncertainty is present, include at "
        "least one evidence item with kind safety_critical_uncertainty. "
        "Do not include provider prices or commercial commitments."
    )


def _model_input(
    turn: RequirementConversationTurn,
    prior_package: Optional[RequirementIntelligencePackage],
):
    payload = {
        "product_surface": turn.product_surface,
        "channel": turn.channel,
        "participant_role": turn.actor_context.participant_role,
        "message": {
            "text": turn.message.text,
            "media": [
                {
                    "kind": item.kind,
                    "media_type": item.media_type,
                    "filename": item.filename,
                }
                for item in turn.message.media
            ],
        },
        "locale": turn.locale,
        "timezone": turn.timezone,
        "prior_requirement_package": (
            prior_package.model_dump(mode="json")
            if prior_package is not None
            else None
        ),
    }
    return json.dumps(payload, ensure_ascii=False)


def _validate_prior_state(
    turn: RequirementConversationTurn,
    prior_package: Optional[RequirementIntelligencePackage],
):
    prior_ref = turn.prior_expert_state

    if prior_ref is None:
        if prior_package is not None:
            raise PriorExpertStateError(
                "Prior package supplied without prior_expert_state reference"
            )
        return uuid4(), 1

    if prior_package is None:
        raise PriorExpertStateError(
            "Continuation turn requires the referenced prior expert package"
        )

    if (
        prior_package.package_id != prior_ref.package_id
        or prior_package.package_version != prior_ref.package_version
    ):
        raise PriorExpertStateError(
            "Prior expert package does not match the continuation reference"
        )

    return prior_package.package_id, prior_package.package_version + 1


def _confidence_map(items):
    result = {}
    for item in items:
        if item.section in result:
            raise RequirementReasoningValidationError(
                "Duplicate confidence section returned by model"
            )
        result[item.section] = item.confidence
    return result


def _build_package(
    parsed: _RequirementModelOutput,
    *,
    package_id,
    package_version,
):
    try:
        service_catalog.get(parsed.domain)
    except KeyError as exc:
        raise RequirementReasoningValidationError(
            "Model returned unsupported service domain"
        ) from exc

    try:
        inspection = InspectionAssessment(
            status=parsed.inspection.status,
            reason=parsed.inspection.reason,
        )
        evidence = [
            RequirementEvidence(
                kind=item.kind,
                statement=item.statement,
                source_reference=item.source_reference,
                confidence=item.confidence,
            )
            for item in parsed.evidence
        ]
        work_packages = [
            RequirementWorkPackage(
                title=item.title,
                description=item.description,
            )
            for item in parsed.work_packages
        ]
    except ValidationError as exc:
        raise RequirementReasoningValidationError(
            "Model returned invalid requirement evidence"
        ) from exc

    safety_escalated = any(
        item.kind == "safety_critical_uncertainty"
        for item in evidence
    )

    ready_for_pricing = (
        parsed.ready_for_pricing
        and not parsed.missing_information
        and not parsed.clarification_questions
        and inspection.status != "required"
        and not safety_escalated
    )

    return RequirementIntelligencePackage(
        package_id=package_id,
        package_version=package_version,
        domain=parsed.domain,
        subdomain=parsed.subdomain,
        customer_objective=parsed.customer_objective,
        interpreted_scope=parsed.interpreted_scope,
        work_packages=work_packages,
        materials_equipment_concepts=parsed.materials_equipment_concepts,
        labour_concepts=parsed.labour_concepts,
        known_quantities=parsed.known_quantities,
        missing_information=parsed.missing_information,
        clarification_questions=parsed.clarification_questions,
        assumptions=parsed.assumptions,
        exclusions=parsed.exclusions,
        safety_compliance=parsed.safety_compliance,
        inspection=inspection,
        environmental_context_constraints=(
            parsed.environmental_context_constraints
        ),
        dependencies=parsed.dependencies,
        ready_for_pricing=ready_for_pricing,
        confidence_by_section=_confidence_map(parsed.confidence_sections),
        evidence=evidence,
    )


def derive_interaction_directive(package: RequirementIntelligencePackage):
    """Deterministic application policy over validated expert evidence."""

    if any(
        item.kind == "safety_critical_uncertainty"
        for item in package.evidence
    ):
        return "safety_escalation"

    if package.inspection.status == "required":
        return "inspection_required"

    if package.clarification_questions:
        return "ask_clarification"

    if package.missing_information:
        return "needs_human_review"

    if package.ready_for_pricing:
        return "ready_for_pricing"

    return "needs_human_review"


def _clarification_draft(package: RequirementIntelligencePackage, directive: str):
    if directive != "ask_clarification":
        return None

    questions = package.clarification_questions
    if len(questions) == 1:
        return questions[0]

    return "To help us understand the requirement:\n" + "\n".join(
        f"{index}. {question}"
        for index, question in enumerate(questions, start=1)
    )


def analyze_requirement_turn(
    turn: RequirementConversationTurn,
    *,
    client,
    prior_package: Optional[RequirementIntelligencePackage] = None,
    metrics=operational_metrics,
    model: str = DEFAULT_REQUIREMENT_MODEL,
):
    """
    Interpret one requirement turn without mutating Quixo or sending messages.

    The model produces evidence. Application code owns package identity/version,
    pricing-readiness guards and the interaction directive.
    """

    package_id, package_version = _validate_prior_state(
        turn,
        prior_package,
    )
    versions = skill_registry.versions(REQUIREMENT_INTELLIGENCE_SKILLS)

    try:
        response = metrics.measure_model_call(
            lambda: client.responses.create(
                model=model,
                instructions=_model_instructions(),
                input=_model_input(turn, prior_package),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "requirement_intelligence",
                        "strict": True,
                        "schema": _strict_json_schema(),
                    }
                },
            )
        )
        parsed = _RequirementModelOutput.model_validate_json(
            response.output_text
        )
    except RequirementReasoningError:
        raise
    except Exception as exc:
        raise RequirementReasoningUnavailableError(
            "Requirement intelligence is temporarily unavailable"
        ) from exc

    package = _build_package(
        parsed,
        package_id=package_id,
        package_version=package_version,
    )
    directive = derive_interaction_directive(package)
    safety_escalated = directive == "safety_escalation"

    return RequirementConversationTurnResponse(
        requirement_package=package,
        directive=directive,
        clarification_questions=package.clarification_questions,
        reply_draft=_clarification_draft(package, directive),
        requires_human_review=directive in {
            "needs_human_review",
            "inspection_required",
            "safety_escalation",
        },
        safety_escalated=safety_escalated,
        provenance=ExpertProvenance(
            analysis_id=uuid4(),
            model=model,
            skill_versions=versions,
        ),
    )
