import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from commercial_contracts import (
    CommercialProposalRequest,
    ProviderCommercialContext,
)
from expert_contracts import (
    InspectionAssessment,
    RequirementEvidence,
    RequirementIntelligencePackage,
)
from expert_commercial_service import (
    CommercialProposalUnavailableError,
    CommercialProposalValidationError,
    analyze_commercial_proposal,
)
from operational_metrics import OperationalMetrics


class CommercialProposalReasoningTests(unittest.TestCase):
    def requirement(self, **overrides):
        payload = {
            "package_id": uuid4(),
            "package_version": 2,
            "domain": "plumbing",
            "customer_objective": "Repair the leaking kitchen tap.",
            "interpreted_scope": ["Inspect and repair the leaking tap."],
            "inspection": InspectionAssessment(status="not_required"),
            "ready_for_pricing": True,
            "evidence": [
                RequirementEvidence(
                    kind="supplied_fact",
                    statement="The kitchen tap is leaking.",
                    confidence=1.0,
                )
            ],
        }
        payload.update(overrides)
        return RequirementIntelligencePackage(**payload)

    def request(self, *, pricing_policy="no_estimates", currency=None, requirement=None):
        return CommercialProposalRequest(
            correlation_id="corr-commercial-1",
            idempotency_key="idem-commercial-1",
            requirement_package=requirement or self.requirement(),
            provider_context=ProviderCommercialContext(
                provider_company_id=uuid4(),
                pricing_policy=pricing_policy,
                preferred_currency=currency,
            ),
        )

    def output(self, **overrides):
        payload = {
            "commercial_summary": "Inspect and repair the leaking kitchen tap.",
            "work_items": [
                {
                    "title": "Tap inspection and repair",
                    "description": "Inspect the tap and repair the confirmed leak source.",
                    "kind": "labour",
                    "quantity_reference": "One kitchen tap",
                    "pricing_evidence": [],
                }
            ],
            "materials_groups": ["Replacement seals or cartridge if required"],
            "labour_groups": ["Plumbing inspection and repair labour"],
            "duration_guidance": {
                "kind": "unknown",
                "minimum_hours": None,
                "maximum_hours": None,
                "basis": None,
                "confidence": None,
            },
            "assumptions": [],
            "exclusions": [],
            "proposal_risks": [],
            "missing_provider_inputs": ["Provider labour rate"],
            "pricing_evidence": [
                {
                    "label": "Provider labour price",
                    "kind": "unknown",
                    "amount_minor": None,
                    "currency": None,
                    "basis": None,
                    "confidence": None,
                }
            ],
            "ready_for_provider_review": True,
        }
        payload.update(overrides)
        return payload

    def client_for(self, payload):
        create = Mock(
            return_value=SimpleNamespace(output_text=json.dumps(payload))
        )
        return SimpleNamespace(responses=SimpleNamespace(create=create))

    def test_no_estimates_policy_returns_unknown_pricing(self):
        request = self.request()
        client = self.client_for(self.output())

        result = analyze_commercial_proposal(request, client=client)

        self.assertEqual(result.pricing_policy, "no_estimates")
        self.assertEqual(result.pricing_evidence[0].kind, "unknown")
        self.assertTrue(result.provider_review_required)
        self.assertEqual(
            result.source_requirement_package_id,
            request.requirement_package.package_id,
        )

    def test_service_carries_forward_requirement_evidence(self):
        request = self.request()
        result = analyze_commercial_proposal(
            request,
            client=self.client_for(self.output()),
        )

        self.assertEqual(result.evidence, request.requirement_package.evidence)

    def test_model_does_not_receive_provider_identity_or_transport_keys(self):
        request = self.request()
        client = self.client_for(self.output())

        analyze_commercial_proposal(request, client=client)

        model_input = client.responses.create.call_args.kwargs["input"]
        self.assertNotIn(
            str(request.provider_context.provider_company_id),
            model_input,
        )
        self.assertNotIn(request.idempotency_key, model_input)
        self.assertNotIn(request.correlation_id, model_input)

    def test_estimate_is_allowed_only_with_policy_and_matching_currency(self):
        estimate = {
            "label": "Indicative labour allowance",
            "kind": "expert_estimate",
            "amount_minor": 18000,
            "currency": "AUD",
            "basis": "Indicative effort only; provider must review.",
            "confidence": 0.55,
        }
        request = self.request(
            pricing_policy="estimates_permitted",
            currency="AUD",
        )
        result = analyze_commercial_proposal(
            request,
            client=self.client_for(
                self.output(pricing_evidence=[estimate])
            ),
        )

        self.assertEqual(result.pricing_evidence[0].kind, "expert_estimate")
        self.assertEqual(result.pricing_evidence[0].currency, "AUD")

    def test_estimate_is_rejected_when_policy_forbids_it(self):
        estimate = {
            "label": "Indicative labour allowance",
            "kind": "expert_estimate",
            "amount_minor": 18000,
            "currency": "AUD",
            "basis": "Indicative only.",
            "confidence": 0.5,
        }

        with self.assertRaises(CommercialProposalValidationError):
            analyze_commercial_proposal(
                self.request(pricing_policy="no_estimates"),
                client=self.client_for(
                    self.output(pricing_evidence=[estimate])
                ),
            )

    def test_estimate_is_rejected_without_matching_currency(self):
        estimate = {
            "label": "Indicative labour allowance",
            "kind": "expert_estimate",
            "amount_minor": 18000,
            "currency": "USD",
            "basis": "Indicative only.",
            "confidence": 0.5,
        }

        with self.assertRaises(CommercialProposalValidationError):
            analyze_commercial_proposal(
                self.request(
                    pricing_policy="estimates_permitted",
                    currency="AUD",
                ),
                client=self.client_for(
                    self.output(pricing_evidence=[estimate])
                ),
            )

    def test_provider_supplied_fact_cannot_be_invented_by_model(self):
        provider_fact = {
            "label": "Provider labour rate",
            "kind": "provider_supplied_fact",
            "amount_minor": 12000,
            "currency": "AUD",
            "basis": "Model claimed provider rate.",
            "confidence": 1.0,
        }

        with self.assertRaises(CommercialProposalValidationError):
            analyze_commercial_proposal(
                self.request(
                    pricing_policy="estimates_permitted",
                    currency="AUD",
                ),
                client=self.client_for(
                    self.output(pricing_evidence=[provider_fact])
                ),
            )

    def test_not_ready_requirement_forces_not_ready_for_provider_review(self):
        requirement = self.requirement(
            ready_for_pricing=False,
            missing_information=["Exact leak point"],
            clarification_questions=["Where is the leak coming from?"],
        )
        request = self.request(requirement=requirement)

        result = analyze_commercial_proposal(
            request,
            client=self.client_for(self.output()),
        )

        self.assertFalse(result.ready_for_provider_review)

    def test_provider_failure_is_sanitized_and_counted(self):
        client = SimpleNamespace(
            responses=SimpleNamespace(
                create=Mock(
                    side_effect=RuntimeError("provider-secret-marker")
                )
            )
        )
        metrics = OperationalMetrics()

        with self.assertRaises(CommercialProposalUnavailableError) as raised:
            analyze_commercial_proposal(
                self.request(),
                client=client,
                metrics=metrics,
            )

        self.assertNotIn("provider-secret-marker", str(raised.exception))
        model = metrics.snapshot()["model_calls"]
        self.assertEqual(model["calls_total"], 1)
        self.assertEqual(model["failures_total"], 1)


if __name__ == "__main__":
    unittest.main()
