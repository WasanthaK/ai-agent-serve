import json
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_skills import skill_registry
from commercial_contracts import (
    CommercialDurationGuidance,
    CommercialMoneyEvidence,
    CommercialProposalPackage,
    CommercialProposalRequest,
    CommercialWorkItem,
)
from operational_metrics import operational_metrics


COMMERCIAL_PROPOSAL_SKILLS = ("commercial_proposal_intelligence",)
DEFAULT_COMMERCIAL_MODEL = "gpt-5.6"


class CommercialProposalReasoningError(Exception):
    """Base error for commercial proposal intelligence."""


class CommercialProposalUnavailableError(CommercialProposalReasoningError):
    """The model provider or structured response was unavailable."""


class CommercialProposalValidationError(CommercialProposalReasoningError):
    """The model response violated deterministic commercial policy."""


class _ModelMoneyEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=500)
    kind: str
    amount_minor: int | None
    currency: str | None
    basis: str | None
    confidence: float | None


class _ModelDurationGuidance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    minimum_hours: float | None
    maximum_hours: float | None
    basis: str | None
    confidence: float | None


class _ModelWorkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    description: str | None
    kind: str
    quantity_reference: str | None
    pricing_evidence: list[_ModelMoneyEvidence]


class _CommercialModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commercial_summary: str = Field(min_length=1, max_length=4000)
    work_items: list[_ModelWorkItem]
    materials_groups: list[str]
    labour_groups: list[str]
    duration_guidance: _ModelDurationGuidance
    assumptions: list[str]
    exclusions: list[str]
    proposal_risks: list[str]
    missing_provider_inputs: list[str]
    pricing_evidence: list[_ModelMoneyEvidence]
    ready_for_provider_review: bool


def _strict_json_schema():
    schema = _CommercialModelOutput.model_json_schema()

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


def _model_instructions(request: CommercialProposalRequest):
    skill = skill_registry.get("commercial_proposal_intelligence")
    policy = request.provider_context.pricing_policy
    currency = request.provider_context.preferred_currency

    policy_text = (
        "Do not produce any expert_estimate monetary values. Use kind=unknown "
        "for pricing not explicitly supplied by the caller."
        if policy == "no_estimates"
        else (
            "Expert estimates are permitted, but each must use kind=expert_estimate, "
            "must be conservative, must include a basis and confidence, and must "
            "use the preferred currency supplied by application context."
        )
    )
    if policy == "estimates_permitted" and currency is None:
        policy_text = (
            "Although estimate policy is enabled, no preferred currency was supplied. "
            "Do not produce numeric monetary estimates; use kind=unknown."
        )

    return (
        f"## Skill: {skill.name} v{skill.version}\n"
        f"{skill.instructions.strip()}\n\n"
        f"Pricing policy: {policy}.\n"
        f"Preferred currency: {currency or 'not supplied'}.\n"
        f"{policy_text}\n\n"
        "Allowed commercial money kinds for this service are only expert_estimate "
        "and unknown. The request contract does not yet carry provider-entered prices, "
        "so never emit provider_supplied_fact or authoritative_platform_fact monetary values. "
        "Allowed work-item kinds: labour, material, equipment, subcontract, allowance, other. "
        "Duration kind may be expert_estimate or unknown. "
        "Do not return authoritative quote totals, tax, discounts, availability, approval, "
        "acceptance, recipient details, or send instructions."
    )


def _model_input(request: CommercialProposalRequest):
    payload = {
        "requirement_package": request.requirement_package.model_dump(mode="json"),
        "provider_context": {
            "pricing_policy": request.provider_context.pricing_policy,
            "preferred_currency": request.provider_context.preferred_currency,
            "locale": request.provider_context.locale,
            "timezone": request.provider_context.timezone,
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _validate_money(
    value: _ModelMoneyEvidence,
    request: CommercialProposalRequest,
):
    if value.kind not in {"expert_estimate", "unknown"}:
        raise CommercialProposalValidationError(
            "Model returned unsupported commercial value kind"
        )

    if value.kind == "expert_estimate":
        if request.provider_context.pricing_policy != "estimates_permitted":
            raise CommercialProposalValidationError(
                "Model returned an expert estimate when estimates are not permitted"
            )
        preferred = request.provider_context.preferred_currency
        if preferred is None or value.currency != preferred:
            raise CommercialProposalValidationError(
                "Expert estimate currency does not match provider context"
            )

    try:
        return CommercialMoneyEvidence(
            label=value.label,
            kind=value.kind,
            amount_minor=value.amount_minor,
            currency=value.currency,
            basis=value.basis,
            confidence=value.confidence,
        )
    except ValidationError as exc:
        raise CommercialProposalValidationError(
            "Model returned invalid commercial pricing evidence"
        ) from exc


def _validate_duration(value: _ModelDurationGuidance):
    if value.kind not in {"expert_estimate", "unknown"}:
        raise CommercialProposalValidationError(
            "Model returned unsupported duration evidence kind"
        )
    try:
        return CommercialDurationGuidance(
            kind=value.kind,
            minimum_hours=value.minimum_hours,
            maximum_hours=value.maximum_hours,
            basis=value.basis,
            confidence=value.confidence,
        )
    except ValidationError as exc:
        raise CommercialProposalValidationError(
            "Model returned invalid duration guidance"
        ) from exc


def _build_package(
    parsed: _CommercialModelOutput,
    request: CommercialProposalRequest,
):
    work_items = []
    for item in parsed.work_items:
        pricing = [
            _validate_money(value, request)
            for value in item.pricing_evidence
        ]
        try:
            work_items.append(
                CommercialWorkItem(
                    title=item.title,
                    description=item.description,
                    kind=item.kind,
                    quantity_reference=item.quantity_reference,
                    pricing_evidence=pricing,
                )
            )
        except ValidationError as exc:
            raise CommercialProposalValidationError(
                "Model returned invalid commercial work item"
            ) from exc

    pricing_evidence = [
        _validate_money(value, request)
        for value in parsed.pricing_evidence
    ]
    duration = _validate_duration(parsed.duration_guidance)

    ready_for_provider_review = (
        parsed.ready_for_provider_review
        and request.requirement_package.ready_for_pricing
        and not request.requirement_package.missing_information
        and not request.requirement_package.clarification_questions
        and request.requirement_package.inspection.status != "required"
    )

    try:
        return CommercialProposalPackage(
            package_id=uuid4(),
            package_version=1,
            source_requirement_package_id=request.requirement_package.package_id,
            source_requirement_package_version=request.requirement_package.package_version,
            provider_company_id=request.provider_context.provider_company_id,
            pricing_policy=request.provider_context.pricing_policy,
            commercial_summary=parsed.commercial_summary,
            work_items=work_items,
            materials_groups=parsed.materials_groups,
            labour_groups=parsed.labour_groups,
            duration_guidance=duration,
            assumptions=parsed.assumptions,
            exclusions=parsed.exclusions,
            proposal_risks=parsed.proposal_risks,
            missing_provider_inputs=parsed.missing_provider_inputs,
            pricing_evidence=pricing_evidence,
            evidence=request.requirement_package.evidence,
            ready_for_provider_review=ready_for_provider_review,
        )
    except ValidationError as exc:
        raise CommercialProposalValidationError(
            "Model output violated commercial proposal policy"
        ) from exc


def analyze_commercial_proposal(
    request: CommercialProposalRequest,
    *,
    client,
    metrics=operational_metrics,
    model: str = DEFAULT_COMMERCIAL_MODEL,
):
    """
    Produce provider-reviewable commercial intelligence without mutating SendQuote.

    Model output is structurally validated and then re-validated against deterministic
    pricing policy. The source Requirement Intelligence Package remains the factual
    evidence base.
    """

    try:
        response = metrics.measure_model_call(
            lambda: client.responses.create(
                model=model,
                instructions=_model_instructions(request),
                input=_model_input(request),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "commercial_proposal_intelligence",
                        "strict": True,
                        "schema": _strict_json_schema(),
                    }
                },
            )
        )
        parsed = _CommercialModelOutput.model_validate_json(
            response.output_text
        )
    except CommercialProposalReasoningError:
        raise
    except Exception as exc:
        raise CommercialProposalUnavailableError(
            "Commercial proposal intelligence is temporarily unavailable"
        ) from exc

    return _build_package(parsed, request)
