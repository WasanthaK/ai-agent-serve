import json
import os
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from openai import OpenAI
from pydantic import BaseModel, Field

from db import (
    database_ready,
    get_request,
    get_request_events,
    get_request_messages,
    record_event,
    save_message,
    save_request,
    update_request_analysis,
    update_request_status,
)
from agent_skills import (
    DEFAULT_ANALYSIS_SKILLS,
    service_catalog,
    skill_registry,
)
from idempotency import (
    complete_webhook_delivery,
    hash_idempotency_key,
    hash_webhook_payload,
    release_webhook_delivery,
    reserve_webhook_delivery,
)
from inbound_adapters import normalize_website_message
from inbound_persistence import (
    InboundMessageConflictError,
    link_inbound_message_to_request,
    save_inbound_message,
)
from observability import (
    StructuredRequestLoggingMiddleware,
    correlation_exception_handler,
)
from operational_metrics import operational_metrics
from provider_selection import (
    ProviderSelectionConflictError,
    ProviderSelectionEligibilityError,
    ProviderSelectionNotFoundError,
    ProviderSelectionStateError,
    ProviderSelectionValidationError,
    get_provider_selection,
    select_providers_for_request,
)
from rfq_handoff import (
    RFQHandoffConflictError,
    RFQHandoffNotFoundError,
    RFQHandoffStateError,
    RFQHandoffValidationError,
    get_rfq_for_request,
    prepare_rfq_handoff,
)
from rfq_delivery import (
    RFQDeliveryConflictError,
    RFQDeliveryEligibilityError,
    RFQDeliveryNotFoundError,
    RFQDeliveryStateError,
    RFQDeliveryValidationError,
    authorize_rfq_delivery,
    confirm_rfq_delivery,
)
from rfq_response import (
    RFQResponseConflictError,
    RFQResponseNotFoundError,
    RFQResponseStateError,
    RFQResponseValidationError,
    ingest_rfq_response,
)
from quote_normalization import (
    QuoteNormalizationConflictError,
    QuoteNormalizationNotFoundError,
    QuoteNormalizationStateError,
    QuoteNormalizationValidationError,
    get_normalized_quote,
    normalize_structured_quote,
)
from quote_completeness import (
    QuoteCompletenessNotFoundError,
    assess_quote_completeness,
)
from quote_comparison import (
    QuoteComparisonNotReadyError,
    compare_request_quotes,
)
from quote_recommendation import (
    QuoteRecommendationConflictError,
    QuoteRecommendationEligibilityError,
    QuoteRecommendationNotFoundError,
    QuoteRecommendationValidationError,
    get_quote_recommendation,
    recommend_quote_for_request,
)
from quote_award import (
    QuoteAwardConflictError,
    QuoteAwardEligibilityError,
    QuoteAwardNotFoundError,
    QuoteAwardValidationError,
    award_recommended_quote,
    get_quote_award,
)
from delivery_handoff import (
    DeliveryHandoffConflictError,
    DeliveryHandoffNotFoundError,
    DeliveryHandoffStateError,
    DeliveryHandoffValidationError,
    activate_delivery_handoff,
    get_delivery_handoff,
)
from delivery_notification import (
    DeliveryNotificationNotFoundError,
    DeliveryNotificationStateError,
    DeliveryNotificationValidationError,
    get_prepared_delivery_notifications,
    prepare_delivery_notifications,
)
from delivery_appointment import (
    DeliveryAppointmentConflictError,
    DeliveryAppointmentNotFoundError,
    DeliveryAppointmentStateError,
    DeliveryAppointmentValidationError,
    confirm_delivery_appointment,
    get_delivery_appointment,
    propose_delivery_appointment,
)
from delivery_status import (
    DeliveryStatusConflictError,
    DeliveryStatusNotFoundError,
    DeliveryStatusStateError,
    DeliveryStatusValidationError,
    complete_delivery,
    get_delivery_status,
    initialize_delivery_status,
    start_delivery,
)
from delivery_exception import (
    DeliveryExceptionConflictError,
    DeliveryExceptionNotFoundError,
    DeliveryExceptionStateError,
    DeliveryExceptionValidationError,
    get_delivery_exceptions,
    record_delivery_exception,
)
from human_intervention import (
    HumanInterventionConflictError,
    HumanInterventionNotFoundError,
    HumanInterventionStateError,
    HumanInterventionValidationError,
    acknowledge_human_intervention,
    create_human_intervention,
    get_human_interventions,
)
from delivery_timeline import (
    DeliveryTimelineValidationError,
    get_delivery_timeline,
)
from satisfaction_follow_up import (
    SatisfactionFollowUpConflictError,
    SatisfactionFollowUpNotFoundError,
    SatisfactionFollowUpStateError,
    SatisfactionFollowUpValidationError,
    get_satisfaction_follow_up,
    prepare_satisfaction_follow_up,
    record_satisfaction_response,
)
from review_request import (
    ReviewRequestConflictError,
    ReviewRequestNotFoundError,
    ReviewRequestStateError,
    ReviewRequestValidationError,
    get_review_request,
    prepare_review_request,
)
from closure_escalation import (
    ClosureEscalationConflictError,
    ClosureEscalationNotFoundError,
    ClosureEscalationStateError,
    ClosureEscalationValidationError,
    create_closure_escalation,
    get_closure_escalations,
)
from outcome_measurement import (
    OutcomeMeasurementNotFoundError,
    OutcomeMeasurementValidationError,
    get_outcome_measurement,
)
from skill_evaluation import (
    SkillEvaluationConflictError,
    SkillEvaluationNotFoundError,
    SkillEvaluationStateError,
    SkillEvaluationValidationError,
    create_skill_evaluation,
    get_skill_evaluations,
)
from skill_improvement import (
    SkillImprovementConflictError,
    SkillImprovementNotFoundError,
    SkillImprovementStateError,
    SkillImprovementValidationError,
    create_skill_improvement_proposal,
    get_skill_improvement_proposals,
)
from skill_regression import (
    SkillRegressionConflictError,
    SkillRegressionNotFoundError,
    SkillRegressionStateError,
    SkillRegressionValidationError,
    get_skill_regression_tests,
    record_skill_regression_test,
)
from skill_revision import (
    SkillRevisionConflictError,
    SkillRevisionNotFoundError,
    SkillRevisionStateError,
    SkillRevisionValidationError,
    create_skill_improvement_revision,
    get_skill_improvement_revisions,
)
from skill_promotion import (
    SkillPromotionConflictError,
    SkillPromotionNotFoundError,
    SkillPromotionStateError,
    SkillPromotionValidationError,
    get_skill_promotions,
    promote_skill,
)
from training_workspace import (
    TrainingWorkspaceNotFoundError,
    TrainingWorkspaceValidationError,
    get_training_case,
    list_training_cases,
)
from training_ui import training_ui_response
from tools import ToolExecutionError, execute_tool, get_tool_version
from security import (
    OperatorPrincipal,
    audit_denial,
    require_inbound_key,
    require_operator_permission,
)


app = FastAPI(
    title="Mac Mini Agent Server",
    version="3.3.0",
)
app.add_middleware(StructuredRequestLoggingMiddleware)
app.add_exception_handler(Exception, correlation_exception_handler)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class AgentRequest(BaseModel):
    message: str


class QuoteWebhookRequest(BaseModel):
    source: str
    customer_name: Optional[str] = None
    message: str


class WorkflowDecision(BaseModel):
    reason: Optional[str] = Field(
        default=None,
        max_length=1000,
    )


class ProviderSelectionDecision(BaseModel):
    service_slug: str = Field(
        min_length=1,
        max_length=120,
    )
    area_key: str = Field(
        min_length=1,
        max_length=120,
    )
    provider_ids: list[UUID]
    reason: Optional[str] = Field(
        default=None,
        max_length=1000,
    )


class RFQDeliveryConfirmation(BaseModel):
    response_deadline_at: datetime


class RFQProviderResponse(BaseModel):
    response_kind: str = Field(min_length=1, max_length=20)
    responded_at: datetime


class NormalizedQuoteInput(BaseModel):
    amount_minor: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    scope_summary: str = Field(min_length=1, max_length=5000)
    exclusions: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    available_from: Optional[date] = None
    estimated_duration_days: Optional[int] = Field(default=None, gt=0)
    validity_expires_at: Optional[datetime] = None


class QuoteRecommendationInput(BaseModel):
    normalized_quote_id: UUID
    rationale: str = Field(min_length=1, max_length=2000)


class QuoteAwardInput(BaseModel):
    recommendation_id: UUID
    reason: str = Field(min_length=1, max_length=2000)


class DeliveryHandoffInput(BaseModel):
    award_id: UUID


class DeliveryAppointmentProposalInput(BaseModel):
    proposed_start_at: datetime
    proposed_end_at: datetime
    reason: str = Field(min_length=1, max_length=2000)


class DeliveryAppointmentConfirmationInput(BaseModel):
    appointment_id: UUID
    reason: str = Field(min_length=1, max_length=2000)


class DeliveryStatusInitializeInput(BaseModel):
    appointment_id: UUID
    reason: str = Field(min_length=1, max_length=2000)


class DeliveryStatusStartInput(BaseModel):
    delivery_status_id: UUID
    reason: str = Field(min_length=1, max_length=2000)


class DeliveryStatusCompleteInput(BaseModel):
    delivery_status_id: UUID
    reason: str = Field(min_length=1, max_length=2000)


class DeliveryExceptionInput(BaseModel):
    exception_id: UUID
    delivery_status_id: UUID
    exception_kind: str = Field(min_length=1, max_length=40)
    occurred_at: datetime
    summary: str = Field(min_length=1, max_length=2000)
    expected_resolution_at: Optional[datetime] = None


class HumanInterventionCreateInput(BaseModel):
    exception_id: UUID
    priority: str = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=2000)


class HumanInterventionAcknowledgeInput(BaseModel):
    intervention_id: UUID
    reason: str = Field(min_length=1, max_length=2000)


class SatisfactionResponseInput(BaseModel):
    follow_up_id: UUID
    rating: int = Field(ge=1, le=5)
    responded_at: datetime
    response_source: str = Field(min_length=1, max_length=100)
    comment: Optional[str] = Field(default=None, max_length=4000)


class ReviewRequestInput(BaseModel):
    satisfaction_follow_up_id: UUID
    reason: str = Field(min_length=1, max_length=2000)


class ClosureEscalationInput(BaseModel):
    satisfaction_follow_up_id: UUID
    escalation_kind: str = Field(min_length=1, max_length=20)
    priority: str = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=4000)


class SkillEvaluationInput(BaseModel):
    analysis_event_id: UUID
    skill_name: str = Field(min_length=1, max_length=120)
    verdict: str = Field(min_length=1, max_length=20)
    notes: str = Field(min_length=1, max_length=4000)


class SkillImprovementProposalInput(BaseModel):
    evaluation_id: UUID
    change_scope: str = Field(min_length=1, max_length=20)
    proposed_change: str = Field(min_length=1, max_length=12000)
    rationale: str = Field(min_length=1, max_length=4000)


class SkillRegressionCaseInput(BaseModel):
    case_id: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=20)
    baseline_result: str = Field(min_length=1, max_length=20)
    candidate_result: str = Field(min_length=1, max_length=20)
    notes: str = Field(min_length=1, max_length=2000)


class SkillRegressionTestInput(BaseModel):
    proposal_id: UUID
    revision_id: Optional[UUID] = None
    suite_name: str = Field(min_length=1, max_length=120)
    suite_version: str = Field(min_length=1, max_length=120)
    cases: list[SkillRegressionCaseInput] = Field(min_length=2, max_length=100)


class SkillImprovementRevisionInput(BaseModel):
    proposal_id: UUID
    proposed_change: str = Field(min_length=1, max_length=12000)
    rationale: str = Field(min_length=1, max_length=4000)


class SkillPromotionInput(BaseModel):
    regression_test_id: UUID
    reason: str = Field(min_length=1, max_length=4000)


class CustomerReply(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=5000,
    )
    channel: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )


class AnalysisResult(dict):
    """Structured analysis plus the exact skill versions used to produce it."""

    def __init__(self, value, *, skill_versions):
        super().__init__(value)
        self.skill_versions = dict(skill_versions)


def analysis_skill_versions_for_result(result):
    versions = getattr(result, "skill_versions", None)
    if versions is not None:
        return dict(versions)
    return skill_registry.versions(DEFAULT_ANALYSIS_SKILLS)


def _analysis_contract_snapshot():
    contract = skill_registry.build_contract(
        DEFAULT_ANALYSIS_SKILLS
    )
    contract["instructions"] = (
        contract["instructions"]
        + "\n\n"
        + service_catalog.build_analysis_instructions()
    )
    return contract


def analyze_quote_request(
    message,
    source="direct",
    customer_name=None,
):
    try:
        contract = _analysis_contract_snapshot()
        response = operational_metrics.measure_model_call(
            lambda: client.responses.create(
                model="gpt-5.6",
                instructions=contract["instructions"],
                input=f"""
Source: {source}
Customer: {customer_name or "Unknown"}
Message or conversation:
{message}
""",
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "quote_request",
                        "strict": True,
                        "schema": contract["schema"],
                    }
                },
            )
        )
        return AnalysisResult(
            json.loads(response.output_text),
            skill_versions=contract["versions"],
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Request analysis is temporarily unavailable",
        ) from None


def _stored_analysis(saved_request):
    return {
        "intent": saved_request["intent"],
        "category": saved_request["category"],
        "summary": saved_request["summary"],
        "urgency": saved_request["urgency"],
        "next_action": saved_request["next_action"],
        "needs_human_review": saved_request["needs_human_review"],
        "missing_information": saved_request["missing_information"],
        "follow_up_questions": saved_request["follow_up_questions"],
    }


def _quote_webhook_response(saved_request):
    return {
        "request_id": saved_request["id"],
        "source": saved_request["source"],
        "customer_name": saved_request["customer_name"],
        "workflow_status": saved_request["status"],
        "analysis": _stored_analysis(saved_request),
    }


@app.get("/")
def health():
    return {
        "status": "running",
        "service": "agent-server",
        "version": "3.3.0",
    }


@app.get("/health/live")
def health_live():
    return {
        "status": "alive",
        "service": "agent-server",
    }


@app.get("/health/ready")
def health_ready():
    if not database_ready():
        raise HTTPException(
            status_code=503,
            detail="Service is not ready",
        )

    return {
        "status": "ready",
        "service": "agent-server",
        "dependencies": {
            "database": "ready",
        },
    }


@app.get("/service-catalog")
def retrieve_service_catalog():
    return service_catalog.as_dict()


@app.get(
    "/metrics/operational",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_operational_metrics():
    return operational_metrics.snapshot()


@app.post("/agent", dependencies=[Depends(require_operator_permission("analyze"))])
def run_agent(request: AgentRequest):
    return analyze_quote_request(
        message=request.message,
        source="direct",
    )


@app.post("/webhook/quote-request")
def quote_webhook(
    request: QuoteWebhookRequest,
    http_request: Request,
    idempotency_key: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key",
    ),
    source: str = Depends(require_inbound_key),
):
    if request.source != source:
        audit_denial(http_request, "source_mismatch", f"channel:{source}")
        raise HTTPException(status_code=403, detail="Source is not authorized")

    key_hash = None
    reserved_request_id = None

    if idempotency_key is not None:
        normalized_key = idempotency_key.strip()
        if not normalized_key or len(normalized_key) > 200:
            raise HTTPException(
                status_code=400,
                detail="Invalid Idempotency-Key",
            )
        key_hash = hash_idempotency_key(normalized_key)

    inbound_message = normalize_website_message(
        authenticated_channel=source,
        text=request.message,
        external_message_id=key_hash,
    )

    if key_hash is not None:
        payload_hash = hash_webhook_payload(
            inbound_message.channel,
            request.customer_name,
            inbound_message.text,
        )
        reservation = reserve_webhook_delivery(
            inbound_message.channel,
            key_hash,
            payload_hash,
        )
        reserved_request_id = reservation["request_id"]

        if reservation["action"] == "conflict":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Idempotency key was already used for a different request"
                ),
            )

        if reservation["action"] == "processing":
            raise HTTPException(
                status_code=409,
                detail="Request with this idempotency key is still processing",
                headers={"Retry-After": "2"},
            )

        if reservation["action"] == "completed":
            saved_request = get_request(reserved_request_id)
            if saved_request is None:
                raise HTTPException(
                    status_code=503,
                    detail="Stored idempotent request is temporarily unavailable",
                )
            try:
                persisted = save_inbound_message(inbound_message)
            except InboundMessageConflictError:
                raise HTTPException(
                    status_code=409,
                    detail="Conflicting website message identity",
                ) from None
            link_inbound_message_to_request(
                persisted["message"]["id"],
                reserved_request_id,
            )
            return _quote_webhook_response(saved_request)

    try:
        persisted = save_inbound_message(inbound_message)
    except InboundMessageConflictError:
        raise HTTPException(
            status_code=409,
            detail="Conflicting website message identity",
        ) from None

    try:
        result = analyze_quote_request(
            message=inbound_message.text,
            source=inbound_message.channel,
            customer_name=request.customer_name,
        )
    except Exception:
        if key_hash is not None:
            release_webhook_delivery(
                inbound_message.channel,
                key_hash,
                reserved_request_id,
            )
        raise

    try:
        request_id = save_request(
            inbound_message.channel,
            request.customer_name,
            inbound_message.text,
            result,
            request_id=reserved_request_id,
            skill_versions=analysis_skill_versions_for_result(result),
        )
    except Exception:
        if key_hash is not None:
            release_webhook_delivery(
                inbound_message.channel,
                key_hash,
                reserved_request_id,
            )
        raise

    saved_request = get_request(request_id)

    if key_hash is not None:
        complete_webhook_delivery(
            inbound_message.channel,
            key_hash,
            request_id,
        )

    link_inbound_message_to_request(
        persisted["message"]["id"],
        request_id,
    )

    return {
        "request_id": request_id,
        "source": inbound_message.channel,
        "customer_name": request.customer_name,
        "workflow_status": saved_request["status"],
        "analysis": result,
    }


@app.get("/requests/{request_id}", dependencies=[Depends(require_operator_permission("read"))])
def retrieve_request(request_id: UUID):
    request = get_request(request_id)

    if request is None:
        raise HTTPException(
            status_code=404,
            detail="Request not found",
        )

    return request


@app.post("/requests/{request_id}/satisfaction-follow-up/response")
def record_request_satisfaction_response(
    request_id: UUID,
    payload: SatisfactionResponseInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return record_satisfaction_response(
            request_id,
            payload.follow_up_id,
            rating=payload.rating,
            responded_at=payload.responded_at,
            response_source=payload.response_source,
            comment=payload.comment,
            actor=operator.actor,
        )
    except SatisfactionFollowUpNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SatisfactionFollowUpValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        SatisfactionFollowUpStateError,
        SatisfactionFollowUpConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/training", include_in_schema=False)
def training_console():
    return training_ui_response()


@app.get(
    "/training/cases",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_training_cases(
    stage: Optional[str] = None,
    skill_name: Optional[str] = None,
    limit: int = 50,
):
    try:
        return {
            "cases": list_training_cases(
                stage=stage,
                skill_name=skill_name,
                limit=limit,
            ),
            "promotion_supported": False,
        }
    except TrainingWorkspaceValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get(
    "/training/cases/{evaluation_id}",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_training_case(evaluation_id: UUID):
    try:
        return get_training_case(evaluation_id)
    except TrainingWorkspaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TrainingWorkspaceValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/skill-promotions",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_skill_promotions(request_id: UUID):
    try:
        return {
            "request_id": str(request_id),
            "promotions": get_skill_promotions(request_id),
        }
    except SkillPromotionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/requests/{request_id}/skill-promotions")
def create_request_skill_promotion(
    request_id: UUID,
    payload: SkillPromotionInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return promote_skill(
            request_id,
            payload.regression_test_id,
            reason=payload.reason,
            actor=operator.actor,
        )
    except SkillPromotionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SkillPromotionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        SkillPromotionStateError,
        SkillPromotionConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/skill-improvement-revisions",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_skill_improvement_revisions(request_id: UUID):
    try:
        return {
            "request_id": str(request_id),
            "revisions": get_skill_improvement_revisions(request_id),
        }
    except SkillRevisionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/requests/{request_id}/skill-improvement-revisions")
def create_request_skill_improvement_revision(
    request_id: UUID,
    payload: SkillImprovementRevisionInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return create_skill_improvement_revision(
            request_id,
            payload.proposal_id,
            proposed_change=payload.proposed_change,
            rationale=payload.rationale,
            actor=operator.actor,
        )
    except SkillRevisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SkillRevisionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        SkillRevisionStateError,
        SkillRevisionConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/skill-regression-tests",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_skill_regression_tests(request_id: UUID):
    try:
        return {
            "request_id": str(request_id),
            "regression_tests": get_skill_regression_tests(request_id),
        }
    except SkillRegressionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/requests/{request_id}/skill-regression-tests")
def create_request_skill_regression_test(
    request_id: UUID,
    payload: SkillRegressionTestInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return record_skill_regression_test(
            request_id,
            payload.proposal_id,
            revision_id=payload.revision_id,
            suite_name=payload.suite_name,
            suite_version=payload.suite_version,
            cases=[case.model_dump() for case in payload.cases],
            actor=operator.actor,
        )
    except SkillRegressionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SkillRegressionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        SkillRegressionStateError,
        SkillRegressionConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/skill-improvement-proposals",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_skill_improvement_proposals(request_id: UUID):
    try:
        return {
            "request_id": str(request_id),
            "proposals": get_skill_improvement_proposals(request_id),
        }
    except SkillImprovementValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/requests/{request_id}/skill-improvement-proposals")
def create_request_skill_improvement_proposal(
    request_id: UUID,
    payload: SkillImprovementProposalInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return create_skill_improvement_proposal(
            request_id,
            payload.evaluation_id,
            change_scope=payload.change_scope,
            proposed_change=payload.proposed_change,
            rationale=payload.rationale,
            actor=operator.actor,
        )
    except SkillImprovementNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SkillImprovementValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        SkillImprovementStateError,
        SkillImprovementConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/skill-evaluations",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_skill_evaluations(request_id: UUID):
    try:
        return {
            "request_id": str(request_id),
            "evaluations": get_skill_evaluations(request_id),
        }
    except SkillEvaluationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/requests/{request_id}/skill-evaluations")
def create_request_skill_evaluation(
    request_id: UUID,
    payload: SkillEvaluationInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return create_skill_evaluation(
            request_id,
            payload.analysis_event_id,
            payload.skill_name,
            verdict=payload.verdict,
            notes=payload.notes,
            actor=operator.actor,
        )
    except SkillEvaluationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SkillEvaluationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        SkillEvaluationStateError,
        SkillEvaluationConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/outcome-measurement",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_outcome_measurement(request_id: UUID):
    try:
        return get_outcome_measurement(request_id)
    except OutcomeMeasurementNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OutcomeMeasurementValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/closure-escalations",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_closure_escalations(request_id: UUID):
    try:
        return {
            "request_id": str(request_id),
            "escalations": get_closure_escalations(request_id),
        }
    except ClosureEscalationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/requests/{request_id}/closure-escalations")
def create_request_closure_escalation(
    request_id: UUID,
    payload: ClosureEscalationInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return create_closure_escalation(
            request_id,
            payload.satisfaction_follow_up_id,
            payload.escalation_kind,
            priority=payload.priority,
            reason=payload.reason,
            actor=operator.actor,
        )
    except ClosureEscalationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ClosureEscalationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        ClosureEscalationStateError,
        ClosureEscalationConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/review-request",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_review_request(request_id: UUID):
    try:
        review_request = get_review_request(request_id)
    except ReviewRequestValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if review_request is None:
        raise HTTPException(
            status_code=404,
            detail="Review request not found",
        )
    return review_request


@app.post("/requests/{request_id}/review-request")
def prepare_request_review_request(
    request_id: UUID,
    payload: ReviewRequestInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return prepare_review_request(
            request_id,
            payload.satisfaction_follow_up_id,
            reason=payload.reason,
            actor=operator.actor,
        )
    except ReviewRequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReviewRequestValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        ReviewRequestStateError,
        ReviewRequestConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/satisfaction-follow-up",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_satisfaction_follow_up(request_id: UUID):
    try:
        follow_up = get_satisfaction_follow_up(request_id)
    except SatisfactionFollowUpValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if follow_up is None:
        raise HTTPException(
            status_code=404,
            detail="Satisfaction follow-up not found",
        )
    return follow_up


@app.post("/requests/{request_id}/satisfaction-follow-up")
def prepare_request_satisfaction_follow_up(
    request_id: UUID,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return prepare_satisfaction_follow_up(
            request_id,
            actor=operator.actor,
        )
    except SatisfactionFollowUpNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SatisfactionFollowUpValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SatisfactionFollowUpStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/delivery-timeline",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_delivery_timeline(request_id: UUID):
    request = get_request(request_id)
    if request is None:
        raise HTTPException(
            status_code=404,
            detail="Request not found",
        )

    try:
        return get_delivery_timeline(request_id)
    except DeliveryTimelineValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/requests/{request_id}/events", dependencies=[Depends(require_operator_permission("read"))])
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


@app.get("/requests/{request_id}/messages", dependencies=[Depends(require_operator_permission("read"))])
def retrieve_request_messages(request_id: UUID):
    request = get_request(request_id)

    if request is None:
        raise HTTPException(
            status_code=404,
            detail="Request not found",
        )

    return {
        "request_id": request_id,
        "original_message": request["message"],
        "messages": get_request_messages(request_id),
    }


@app.post("/requests/{request_id}/reply")
def receive_customer_reply(
    request_id: UUID,
    reply: CustomerReply,
    operator: OperatorPrincipal = Depends(require_operator_permission("reply")),
):
    request = get_request(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")

    return _process_customer_reply(
        request_id, reply, request,
        channel=reply.channel or request["source"],
        actor=operator.actor,
    )


@app.post("/webhook/quote-request/{request_id}/reply")
def receive_channel_reply(
    request_id: UUID,
    reply: CustomerReply,
    http_request: Request,
    source: str = Depends(require_inbound_key),
):
    request = get_request(request_id)

    if request is None or request["source"] != source:
        audit_denial(http_request, "channel_request_denied", f"channel:{source}")
        raise HTTPException(status_code=404, detail="Request not found")

    if reply.channel is not None and reply.channel != source:
        audit_denial(http_request, "channel_mismatch", f"channel:{source}")
        raise HTTPException(status_code=403, detail="Channel is not authorized")

    return _process_customer_reply(
        request_id, reply, request, channel=source, actor=f"channel:{source}"
    )


def _process_customer_reply(request_id, reply, request, channel, actor):
    if request["status"] != "needs_information":
        raise HTTPException(
            status_code=409,
            detail=(
                "Customer replies can only be added while information "
                f"is required. Current status: {request['status']}"
            ),
        )

    saved_message = save_message(
        request_id=request_id,
        role="customer",
        channel=channel,
        message=reply.message,
        actor=actor,
    )

    messages = get_request_messages(request_id)

    conversation_lines = [
        f"Original customer request: {request['message']}"
    ]

    for message in messages:
        conversation_lines.append(
            f"{message['role'].title()} reply: {message['message']}"
        )

    conversation = "\n".join(conversation_lines)

    try:
        result = analyze_quote_request(
            message=conversation,
            source=request["source"],
            customer_name=request["customer_name"],
        )
    except Exception as exc:
        record_event(
            request_id=request_id,
            event_type="reanalysis_failed",
            actor="agent",
            details={
                "error_type": type(exc).__name__,
            },
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "The reply was saved, but the request could not "
                "be reanalysed."
            ),
        ) from exc

    updated_request = update_request_analysis(
        request_id=request_id,
        result=result,
        skill_versions=analysis_skill_versions_for_result(result),
    )

    return {
        "request_id": request_id,
        "message": saved_message,
        "workflow_status": updated_request["status"],
        "analysis": result,
    }


@app.get(
    "/requests/{request_id}/provider-selection",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_provider_selection(request_id: UUID):
    try:
        selection = get_provider_selection(request_id)
    except ProviderSelectionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if selection is None:
        raise HTTPException(
            status_code=404,
            detail="Provider selection not found",
        )

    return selection


@app.post("/requests/{request_id}/provider-selection")
def select_request_providers(
    request_id: UUID,
    decision: ProviderSelectionDecision,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return select_providers_for_request(
            request_id,
            decision.service_slug,
            decision.area_key,
            decision.provider_ids,
            actor=operator.actor,
            reason=decision.reason,
        )
    except ProviderSelectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProviderSelectionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        ProviderSelectionStateError,
        ProviderSelectionEligibilityError,
        ProviderSelectionConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/rfq-handoff",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_rfq_handoff(request_id: UUID):
    try:
        rfq = get_rfq_for_request(request_id)
    except RFQHandoffValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if rfq is None:
        raise HTTPException(status_code=404, detail="RFQ handoff not found")

    return rfq


@app.post("/requests/{request_id}/rfq-handoff")
def prepare_request_rfq_handoff(
    request_id: UUID,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return prepare_rfq_handoff(
            request_id,
            actor=operator.actor,
        )
    except RFQHandoffNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RFQHandoffValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        RFQHandoffStateError,
        RFQHandoffConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/requests/{request_id}/rfq-handoffs/{handoff_id}/authorize-delivery"
)
def authorize_request_rfq_delivery(
    request_id: UUID,
    handoff_id: UUID,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return authorize_rfq_delivery(
            request_id,
            handoff_id,
            actor=operator.actor,
        )
    except RFQDeliveryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RFQDeliveryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        RFQDeliveryStateError,
        RFQDeliveryEligibilityError,
        RFQDeliveryConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/requests/{request_id}/rfq-handoffs/{handoff_id}/confirm-delivery"
)
def confirm_request_rfq_delivery(
    request_id: UUID,
    handoff_id: UUID,
    confirmation: RFQDeliveryConfirmation,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return confirm_rfq_delivery(
            request_id,
            handoff_id,
            confirmation.response_deadline_at,
            actor=operator.actor,
        )
    except RFQDeliveryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RFQDeliveryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        RFQDeliveryStateError,
        RFQDeliveryEligibilityError,
        RFQDeliveryConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/requests/{request_id}/rfq-handoffs/{handoff_id}/provider-response"
)
def record_request_rfq_provider_response(
    request_id: UUID,
    handoff_id: UUID,
    response: RFQProviderResponse,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return ingest_rfq_response(
            request_id,
            handoff_id,
            response.response_kind,
            response.responded_at,
            actor=operator.actor,
        )
    except RFQResponseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RFQResponseValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        RFQResponseStateError,
        RFQResponseConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/rfq-handoffs/{handoff_id}/normalized-quote",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_normalized_quote(
    request_id: UUID,
    handoff_id: UUID,
):
    try:
        quote = get_normalized_quote(request_id, handoff_id)
    except QuoteNormalizationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if quote is None:
        raise HTTPException(status_code=404, detail="Normalized quote not found")

    return quote


@app.post(
    "/requests/{request_id}/rfq-handoffs/{handoff_id}/normalized-quote"
)
def record_normalized_quote(
    request_id: UUID,
    handoff_id: UUID,
    quote: NormalizedQuoteInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return normalize_structured_quote(
            request_id,
            handoff_id,
            amount_minor=quote.amount_minor,
            currency=quote.currency,
            scope_summary=quote.scope_summary,
            exclusions=quote.exclusions,
            terms=quote.terms,
            available_from=quote.available_from,
            estimated_duration_days=quote.estimated_duration_days,
            validity_expires_at=quote.validity_expires_at,
            actor=operator.actor,
        )
    except QuoteNormalizationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QuoteNormalizationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        QuoteNormalizationStateError,
        QuoteNormalizationConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/rfq-handoffs/{handoff_id}/quote-completeness",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_quote_completeness(
    request_id: UUID,
    handoff_id: UUID,
):
    try:
        return assess_quote_completeness(request_id, handoff_id)
    except QuoteCompletenessNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/quote-comparison",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_quote_comparison(request_id: UUID):
    try:
        return compare_request_quotes(request_id)
    except QuoteComparisonNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/quote-recommendation",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_quote_recommendation(request_id: UUID):
    try:
        recommendation = get_quote_recommendation(request_id)
    except QuoteRecommendationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if recommendation is None:
        raise HTTPException(
            status_code=404,
            detail="Quote recommendation not found",
        )
    return recommendation


@app.post("/requests/{request_id}/quote-recommendation")
def record_quote_recommendation(
    request_id: UUID,
    recommendation: QuoteRecommendationInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return recommend_quote_for_request(
            request_id,
            recommendation.normalized_quote_id,
            rationale=recommendation.rationale,
            actor=operator.actor,
        )
    except QuoteRecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QuoteRecommendationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        QuoteRecommendationEligibilityError,
        QuoteRecommendationConflictError,
        QuoteComparisonNotReadyError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/quote-award",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_quote_award(request_id: UUID):
    try:
        award = get_quote_award(request_id)
    except QuoteAwardValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if award is None:
        raise HTTPException(status_code=404, detail="Quote award not found")
    return award


@app.post("/requests/{request_id}/quote-award")
def record_quote_award(
    request_id: UUID,
    award: QuoteAwardInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return award_recommended_quote(
            request_id,
            award.recommendation_id,
            reason=award.reason,
            actor=operator.actor,
        )
    except QuoteAwardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QuoteAwardValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        QuoteAwardEligibilityError,
        QuoteAwardConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/delivery-handoff",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_delivery_handoff(request_id: UUID):
    try:
        handoff = get_delivery_handoff(request_id)
    except DeliveryHandoffValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if handoff is None:
        raise HTTPException(
            status_code=404,
            detail="Delivery handoff not found",
        )
    return handoff


@app.post("/requests/{request_id}/delivery-handoff")
def activate_request_delivery_handoff(
    request_id: UUID,
    payload: DeliveryHandoffInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return activate_delivery_handoff(
            request_id,
            payload.award_id,
            actor=operator.actor,
        )
    except DeliveryHandoffNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeliveryHandoffValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        DeliveryHandoffStateError,
        DeliveryHandoffConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/delivery-notifications",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_delivery_notifications(request_id: UUID):
    try:
        notifications = get_prepared_delivery_notifications(request_id)
    except DeliveryNotificationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not notifications:
        raise HTTPException(
            status_code=404,
            detail="Prepared delivery notifications not found",
        )

    return {
        "request_id": str(request_id),
        "notifications": notifications,
        "destinations_resolved": False,
        "sent": False,
    }


@app.post("/requests/{request_id}/delivery-notifications")
def prepare_request_delivery_notifications(
    request_id: UUID,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return prepare_delivery_notifications(
            request_id,
            actor=operator.actor,
        )
    except DeliveryNotificationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeliveryNotificationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DeliveryNotificationStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/delivery-appointment",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_delivery_appointment(request_id: UUID):
    try:
        appointment = get_delivery_appointment(request_id)
    except DeliveryAppointmentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if appointment is None:
        raise HTTPException(
            status_code=404,
            detail="Delivery appointment not found",
        )
    return appointment


@app.post("/requests/{request_id}/delivery-appointment/proposal")
def propose_request_delivery_appointment(
    request_id: UUID,
    payload: DeliveryAppointmentProposalInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return propose_delivery_appointment(
            request_id,
            payload.proposed_start_at,
            payload.proposed_end_at,
            reason=payload.reason,
            actor=operator.actor,
        )
    except DeliveryAppointmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeliveryAppointmentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        DeliveryAppointmentStateError,
        DeliveryAppointmentConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/requests/{request_id}/delivery-appointment/confirmation")
def confirm_request_delivery_appointment(
    request_id: UUID,
    payload: DeliveryAppointmentConfirmationInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return confirm_delivery_appointment(
            request_id,
            payload.appointment_id,
            reason=payload.reason,
            actor=operator.actor,
        )
    except DeliveryAppointmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeliveryAppointmentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        DeliveryAppointmentStateError,
        DeliveryAppointmentConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/delivery-status",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_delivery_status(request_id: UUID):
    try:
        status = get_delivery_status(request_id)
    except DeliveryStatusValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if status is None:
        raise HTTPException(
            status_code=404,
            detail="Delivery status not found",
        )
    return status


@app.post("/requests/{request_id}/delivery-status/schedule")
def schedule_request_delivery(
    request_id: UUID,
    payload: DeliveryStatusInitializeInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return initialize_delivery_status(
            request_id,
            payload.appointment_id,
            reason=payload.reason,
            actor=operator.actor,
        )
    except DeliveryStatusNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeliveryStatusValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        DeliveryStatusStateError,
        DeliveryStatusConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/requests/{request_id}/delivery-status/start")
def start_request_delivery(
    request_id: UUID,
    payload: DeliveryStatusStartInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return start_delivery(
            request_id,
            payload.delivery_status_id,
            reason=payload.reason,
            actor=operator.actor,
        )
    except DeliveryStatusNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeliveryStatusValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        DeliveryStatusStateError,
        DeliveryStatusConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/requests/{request_id}/delivery-status/complete")
def complete_request_delivery(
    request_id: UUID,
    payload: DeliveryStatusCompleteInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return complete_delivery(
            request_id,
            payload.delivery_status_id,
            reason=payload.reason,
            actor=operator.actor,
        )
    except DeliveryStatusNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeliveryStatusValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        DeliveryStatusStateError,
        DeliveryStatusConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/delivery-exceptions",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_delivery_exceptions(request_id: UUID):
    try:
        return {
            "request_id": str(request_id),
            "exceptions": get_delivery_exceptions(request_id),
        }
    except DeliveryExceptionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/requests/{request_id}/delivery-exceptions")
def record_request_delivery_exception(
    request_id: UUID,
    payload: DeliveryExceptionInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return record_delivery_exception(
            request_id,
            payload.delivery_status_id,
            payload.exception_id,
            payload.exception_kind,
            payload.occurred_at,
            summary=payload.summary,
            expected_resolution_at=payload.expected_resolution_at,
            actor=operator.actor,
        )
    except DeliveryExceptionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeliveryExceptionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        DeliveryExceptionStateError,
        DeliveryExceptionConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/requests/{request_id}/human-interventions",
    dependencies=[Depends(require_operator_permission("read"))],
)
def retrieve_human_interventions(request_id: UUID):
    try:
        return {
            "request_id": str(request_id),
            "interventions": get_human_interventions(request_id),
        }
    except HumanInterventionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/requests/{request_id}/human-interventions")
def create_request_human_intervention(
    request_id: UUID,
    payload: HumanInterventionCreateInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return create_human_intervention(
            request_id,
            payload.exception_id,
            priority=payload.priority,
            reason=payload.reason,
            actor=operator.actor,
        )
    except HumanInterventionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HumanInterventionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        HumanInterventionStateError,
        HumanInterventionConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/requests/{request_id}/human-interventions/acknowledge")
def acknowledge_request_human_intervention(
    request_id: UUID,
    payload: HumanInterventionAcknowledgeInput,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
):
    try:
        return acknowledge_human_intervention(
            request_id,
            payload.intervention_id,
            reason=payload.reason,
            actor=operator.actor,
        )
    except HumanInterventionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HumanInterventionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        HumanInterventionStateError,
        HumanInterventionConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/requests/{request_id}/approve")
def approve_request(
    request_id: UUID,
    decision: WorkflowDecision,
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
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
        actor=operator.actor,
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
    operator: OperatorPrincipal = Depends(require_operator_permission("decide")),
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
        actor=operator.actor,
        event_type="request_rejected",
        details={
            "reason": decision.reason,
        },
    )

    return updated


@app.post("/requests/{request_id}/tools/{tool_name}")
def run_request_tool(
    request_id: UUID,
    tool_name: str,
    operator: OperatorPrincipal = Depends(require_operator_permission("tools")),
):
    request = get_request(request_id)

    if request is None:
        raise HTTPException(
            status_code=404,
            detail="Request not found",
        )

    allowed_tools_by_status = {
        "needs_information": {
            "prepare_customer_follow_up",
        },
    }

    allowed_tools = allowed_tools_by_status.get(
        request["status"],
        set(),
    )

    if tool_name not in allowed_tools:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Tool '{tool_name}' is not allowed when the "
                f"request status is '{request['status']}'."
            ),
        )

    tool_version = get_tool_version(tool_name)

    record_event(
        request_id=request_id,
        event_type="tool_started",
        actor=operator.actor,
        details={
            "tool": tool_name,
            "tool_version": tool_version,
        },
    )

    try:
        result = execute_tool(
            tool_name=tool_name,
            request=request,
        )
    except ToolExecutionError as exc:
        record_event(
            request_id=request_id,
            event_type="tool_failed",
            actor=operator.actor,
            details={
                "tool": tool_name,
                "tool_version": tool_version,
                "error_type": type(exc).__name__,
            },
        )

        raise HTTPException(
            status_code=422,
            detail="Tool could not be executed",
        ) from exc

    record_event(
        request_id=request_id,
        event_type="tool_completed",
        actor=operator.actor,
        details={
            "tool": tool_name,
            "tool_version": tool_version,
        },
    )

    return {
        "request_id": request_id,
        "status": request["status"],
        "result": result,
    }
