from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from expert_contracts import (
    RequirementBusinessReferences,
    RequirementEvidence,
    RequirementIntelligencePackage,
)


CommercialPricingPolicy = Literal[
    "no_estimates",
    "estimates_permitted",
]

CommercialValueKind = Literal[
    "provider_supplied_fact",
    "authoritative_platform_fact",
    "expert_estimate",
    "unknown",
]

CommercialWorkItemKind = Literal[
    "labour",
    "material",
    "equipment",
    "subcontract",
    "allowance",
    "other",
]


class ProviderCommercialContext(BaseModel):
    """Explicit provider context supplied by the owning Quixo product."""

    model_config = ConfigDict(extra="forbid")

    provider_company_id: UUID
    pricing_policy: CommercialPricingPolicy = "no_estimates"
    preferred_currency: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
    )
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


class CommercialProposalRequest(BaseModel):
    """Stateless provider-side input contract for commercial proposal intelligence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    correlation_id: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=500)
    requirement_package: RequirementIntelligencePackage
    provider_context: ProviderCommercialContext
    business_references: RequirementBusinessReferences = Field(
        default_factory=RequirementBusinessReferences
    )


class CommercialMoneyEvidence(BaseModel):
    """
    A provider-reviewable monetary fact or estimate.

    This is evidence only. It is never an authoritative quote line, subtotal,
    tax, total, approval or send instruction.
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=500)
    kind: CommercialValueKind
    amount_minor: Optional[int] = Field(default=None, ge=0)
    currency: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
    )
    basis: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=4000,
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    provider_review_required: Literal[True] = True

    @model_validator(mode="after")
    def validate_value_semantics(self):
        if self.kind == "unknown":
            if self.amount_minor is not None or self.currency is not None:
                raise ValueError(
                    "Unknown commercial values must not carry an amount or currency"
                )
            return self

        if self.amount_minor is None or self.currency is None:
            raise ValueError(
                "Known commercial values require both amount_minor and currency"
            )
        return self


class CommercialDurationGuidance(BaseModel):
    """Provider-reviewable duration evidence; never a booking or availability promise."""

    model_config = ConfigDict(extra="forbid")

    kind: CommercialValueKind
    minimum_hours: Optional[float] = Field(default=None, ge=0)
    maximum_hours: Optional[float] = Field(default=None, ge=0)
    basis: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=4000,
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    provider_review_required: Literal[True] = True

    @model_validator(mode="after")
    def validate_duration_semantics(self):
        if self.kind == "unknown":
            if self.minimum_hours is not None or self.maximum_hours is not None:
                raise ValueError(
                    "Unknown duration must not carry numeric duration values"
                )
            return self

        if self.minimum_hours is None and self.maximum_hours is None:
            raise ValueError(
                "Known duration guidance requires at least one duration value"
            )
        if (
            self.minimum_hours is not None
            and self.maximum_hours is not None
            and self.maximum_hours < self.minimum_hours
        ):
            raise ValueError(
                "maximum_hours cannot be less than minimum_hours"
            )
        return self


class CommercialWorkItem(BaseModel):
    """Provider-reviewable commercial work structure derived from the requirement."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    description: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=4000,
    )
    kind: CommercialWorkItemKind
    quantity_reference: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=1000,
    )
    pricing_evidence: list[CommercialMoneyEvidence] = Field(
        default_factory=list,
        max_length=20,
    )


class CommercialProposalPackage(BaseModel):
    """
    Provider-side commercial intelligence package.

    It deliberately has no subtotal, tax, total, approval, acceptance or send
    fields. SendQuote remains authoritative for the actual quotation.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    package_id: UUID
    package_version: int = Field(ge=1)
    source_requirement_package_id: UUID
    source_requirement_package_version: int = Field(ge=1)
    provider_company_id: UUID
    pricing_policy: CommercialPricingPolicy
    commercial_summary: str = Field(min_length=1, max_length=4000)
    work_items: list[CommercialWorkItem] = Field(
        default_factory=list,
        max_length=100,
    )
    materials_groups: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    labour_groups: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    duration_guidance: CommercialDurationGuidance
    assumptions: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    exclusions: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    proposal_risks: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    missing_provider_inputs: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    pricing_evidence: list[CommercialMoneyEvidence] = Field(
        default_factory=list,
        max_length=100,
    )
    evidence: list[RequirementEvidence] = Field(
        default_factory=list,
        max_length=200,
    )
    ready_for_provider_review: bool
    provider_review_required: Literal[True] = True

    @model_validator(mode="after")
    def enforce_pricing_policy(self):
        if self.pricing_policy == "estimates_permitted":
            return self

        all_pricing = list(self.pricing_evidence)
        for item in self.work_items:
            all_pricing.extend(item.pricing_evidence)

        if any(value.kind == "expert_estimate" for value in all_pricing):
            raise ValueError(
                "Expert pricing estimates are not permitted by this package policy"
            )
        return self
