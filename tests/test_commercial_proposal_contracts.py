import unittest
from uuid import uuid4

from pydantic import ValidationError

from commercial_contracts import (
    CommercialDurationGuidance,
    CommercialMoneyEvidence,
    CommercialProposalPackage,
    CommercialProposalRequest,
    CommercialWorkItem,
    ProviderCommercialContext,
)
from expert_contracts import (
    InspectionAssessment,
    RequirementIntelligencePackage,
)


class CommercialProposalContractTests(unittest.TestCase):
    def requirement_package(self):
        return RequirementIntelligencePackage(
            package_id=uuid4(),
            package_version=3,
            domain="plumbing",
            customer_objective="Repair a leaking kitchen tap.",
            interpreted_scope=[
                "Inspect the tap and repair the confirmed leak source."
            ],
            inspection=InspectionAssessment(status="not_required"),
            ready_for_pricing=True,
        )

    def package(self, **overrides):
        requirement = self.requirement_package()
        payload = {
            "package_id": uuid4(),
            "package_version": 1,
            "source_requirement_package_id": requirement.package_id,
            "source_requirement_package_version": requirement.package_version,
            "provider_company_id": uuid4(),
            "pricing_policy": "no_estimates",
            "commercial_summary": (
                "Provider-reviewable structure for inspecting and repairing "
                "the leaking kitchen tap."
            ),
            "work_items": [
                CommercialWorkItem(
                    title="Inspect and repair kitchen tap",
                    kind="labour",
                    quantity_reference="One kitchen tap",
                    pricing_evidence=[],
                )
            ],
            "duration_guidance": CommercialDurationGuidance(
                kind="unknown",
            ),
            "ready_for_provider_review": True,
        }
        payload.update(overrides)
        return CommercialProposalPackage(**payload)

    def test_request_binds_requirement_to_explicit_provider_context(self):
        requirement = self.requirement_package()
        company_id = uuid4()

        request = CommercialProposalRequest(
            correlation_id="corr-commercial-1",
            idempotency_key="idem-commercial-1",
            requirement_package=requirement,
            provider_context=ProviderCommercialContext(
                provider_company_id=company_id,
                pricing_policy="no_estimates",
                preferred_currency="AUD",
            ),
        )

        self.assertEqual(request.schema_version, "1.0")
        self.assertEqual(
            request.provider_context.provider_company_id,
            company_id,
        )
        self.assertEqual(
            request.requirement_package.package_id,
            requirement.package_id,
        )

    def test_package_has_no_authoritative_quote_totals_or_send_fields(self):
        package = self.package()
        payload = package.model_dump()

        for forbidden in (
            "subtotal",
            "subtotal_minor",
            "tax",
            "tax_minor",
            "total",
            "total_minor",
            "approved",
            "accepted",
            "recipient",
            "send",
            "send_quote",
        ):
            self.assertNotIn(forbidden, payload)

    def test_unknown_money_value_cannot_smuggle_amount(self):
        with self.assertRaises(ValidationError):
            CommercialMoneyEvidence(
                label="Unknown material allowance",
                kind="unknown",
                amount_minor=25000,
                currency="AUD",
            )

    def test_known_money_value_requires_amount_and_currency(self):
        with self.assertRaises(ValidationError):
            CommercialMoneyEvidence(
                label="Provider labour rate",
                kind="provider_supplied_fact",
                amount_minor=12000,
            )

    def test_no_estimates_policy_rejects_expert_price_estimate(self):
        estimate = CommercialMoneyEvidence(
            label="Possible labour allowance",
            kind="expert_estimate",
            amount_minor=18000,
            currency="AUD",
            basis="Indicative only; provider must review.",
            confidence=0.6,
        )

        with self.assertRaises(ValidationError):
            self.package(
                pricing_policy="no_estimates",
                pricing_evidence=[estimate],
            )

    def test_estimate_policy_allows_clearly_labelled_provider_reviewable_estimate(self):
        estimate = CommercialMoneyEvidence(
            label="Possible labour allowance",
            kind="expert_estimate",
            amount_minor=18000,
            currency="AUD",
            basis="Indicative only; provider must review.",
            confidence=0.6,
        )

        package = self.package(
            pricing_policy="estimates_permitted",
            pricing_evidence=[estimate],
        )

        self.assertEqual(
            package.pricing_evidence[0].kind,
            "expert_estimate",
        )
        self.assertTrue(
            package.pricing_evidence[0].provider_review_required
        )
        self.assertTrue(package.provider_review_required)

    def test_provider_review_cannot_be_disabled(self):
        with self.assertRaises(ValidationError):
            self.package(provider_review_required=False)

    def test_duration_guidance_is_not_an_availability_promise(self):
        duration = CommercialDurationGuidance(
            kind="expert_estimate",
            minimum_hours=1.0,
            maximum_hours=2.5,
            basis="Typical repair effort after diagnosis.",
            confidence=0.5,
        )

        package = self.package(
            pricing_policy="estimates_permitted",
            duration_guidance=duration,
        )

        self.assertEqual(
            package.duration_guidance.maximum_hours,
            2.5,
        )
        self.assertNotIn(
            "available_from",
            package.duration_guidance.model_dump(),
        )

    def test_unknown_fields_are_rejected(self):
        package = self.package()

        with self.assertRaises(ValidationError):
            CommercialProposalPackage(
                **package.model_dump(),
                final_quote_total_minor=50000,
            )


if __name__ == "__main__":
    unittest.main()
