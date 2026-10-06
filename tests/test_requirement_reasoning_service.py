import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from operational_metrics import OperationalMetrics
from expert_contracts import (
    AgentExecutionContext,
    InspectionAssessment,
    PriorExpertState,
    RequirementConversationTurn,
    RequirementIntelligencePackage,
    RequirementTurnMessage,
)
from expert_requirement_service import (
    PriorExpertStateError,
    RequirementReasoningUnavailableError,
    RequirementReasoningValidationError,
    analyze_requirement_turn,
)


class RequirementReasoningServiceTests(unittest.TestCase):
    def turn(self, **overrides):
        payload = {
            "product_surface": "widget",
            "channel": "web",
            "correlation_id": "corr-1",
            "idempotency_key": "idem-1",
            "message": RequirementTurnMessage(
                external_message_id="transport-msg-1",
                external_thread_id="transport-thread-1",
                text="My kitchen tap is leaking.",
            ),
            "actor_context": AgentExecutionContext(
                participant_role="customer",
                provider_company_id=uuid4(),
                identity_user_id=uuid4(),
                public_reference="public-secret-reference",
            ),
        }
        payload.update(overrides)
        return RequirementConversationTurn(**payload)

    def model_payload(self, **overrides):
        payload = {
            "domain": "plumbing",
            "subdomain": "tap-repair",
            "customer_objective": "Stop the kitchen tap leak.",
            "interpreted_scope": [
                "Inspect the kitchen tap and identify the leak source."
            ],
            "work_packages": [
                {
                    "title": "Tap inspection",
                    "description": "Inspect the affected tap and connections.",
                }
            ],
            "materials_equipment_concepts": [],
            "labour_concepts": ["Plumbing inspection and repair labour"],
            "known_quantities": ["One kitchen tap"],
            "missing_information": [
                "Exact leak point is not yet known."
            ],
            "clarification_questions": [
                "Where is the water leaking from: the spout, handle, or pipe connection?"
            ],
            "assumptions": [],
            "exclusions": [],
            "safety_compliance": [],
            "inspection": {
                "status": "unknown",
                "reason": None,
            },
            "environmental_context_constraints": [],
            "dependencies": [],
            "ready_for_pricing": False,
            "confidence_sections": [
                {"section": "domain", "confidence": 0.98},
                {"section": "scope", "confidence": 0.70},
            ],
            "evidence": [
                {
                    "kind": "supplied_fact",
                    "statement": "The kitchen tap is leaking.",
                    "source_reference": "customer_message",
                    "confidence": 1.0,
                }
            ],
        }
        payload.update(overrides)
        return payload

    def client_for(self, payload):
        create = Mock(
            return_value=SimpleNamespace(
                output_text=json.dumps(payload)
            )
        )
        return SimpleNamespace(
            responses=SimpleNamespace(create=create)
        )

    def test_missing_information_returns_clarification_directive(self):
        client = self.client_for(self.model_payload())

        result = analyze_requirement_turn(
            self.turn(),
            client=client,
        )

        self.assertEqual(result.directive, "ask_clarification")
        self.assertFalse(result.requirement_package.ready_for_pricing)
        self.assertEqual(result.requirement_package.package_version, 1)
        self.assertIsNotNone(result.reply_draft)
        self.assertEqual(
            result.provenance.skill_versions,
            {"requirement_intelligence": "1.0.0"},
        )

    def test_model_never_receives_transport_or_identity_authority_data(self):
        turn = self.turn()
        client = self.client_for(self.model_payload())

        analyze_requirement_turn(turn, client=client)

        model_input = client.responses.create.call_args.kwargs["input"]
        self.assertNotIn(str(turn.actor_context.provider_company_id), model_input)
        self.assertNotIn(str(turn.actor_context.identity_user_id), model_input)
        self.assertNotIn(turn.actor_context.public_reference, model_input)
        self.assertNotIn(turn.idempotency_key, model_input)
        self.assertNotIn(turn.message.external_message_id, model_input)
        self.assertNotIn(turn.message.external_thread_id, model_input)

    def test_application_forces_not_ready_when_model_has_open_questions(self):
        payload = self.model_payload(ready_for_pricing=True)
        result = analyze_requirement_turn(
            self.turn(),
            client=self.client_for(payload),
        )

        self.assertFalse(result.requirement_package.ready_for_pricing)
        self.assertEqual(result.directive, "ask_clarification")

    def test_safety_critical_evidence_has_highest_precedence(self):
        payload = self.model_payload(
            missing_information=[],
            clarification_questions=[],
            ready_for_pricing=True,
            evidence=[
                {
                    "kind": "safety_critical_uncertainty",
                    "statement": "Customer reports exposed live wiring near water.",
                    "source_reference": "customer_message",
                    "confidence": 0.95,
                }
            ],
        )

        result = analyze_requirement_turn(
            self.turn(),
            client=self.client_for(payload),
        )

        self.assertEqual(result.directive, "safety_escalation")
        self.assertTrue(result.safety_escalated)
        self.assertTrue(result.requires_human_review)
        self.assertFalse(result.requirement_package.ready_for_pricing)

    def test_required_inspection_prevents_pricing_readiness(self):
        payload = self.model_payload(
            missing_information=[],
            clarification_questions=[],
            ready_for_pricing=True,
            inspection={
                "status": "required",
                "reason": "The concealed leak source cannot be scoped remotely.",
            },
        )

        result = analyze_requirement_turn(
            self.turn(),
            client=self.client_for(payload),
        )

        self.assertEqual(result.directive, "inspection_required")
        self.assertFalse(result.requirement_package.ready_for_pricing)

    def test_ready_package_returns_ready_for_pricing(self):
        payload = self.model_payload(
            missing_information=[],
            clarification_questions=[],
            ready_for_pricing=True,
            inspection={
                "status": "not_required",
                "reason": None,
            },
        )

        result = analyze_requirement_turn(
            self.turn(),
            client=self.client_for(payload),
        )

        self.assertEqual(result.directive, "ready_for_pricing")
        self.assertTrue(result.requirement_package.ready_for_pricing)
        self.assertIsNone(result.reply_draft)

    def test_continuation_reuses_package_id_and_increments_version(self):
        package_id = uuid4()
        prior = RequirementIntelligencePackage(
            package_id=package_id,
            package_version=3,
            domain="plumbing",
            customer_objective="Repair a leaking tap.",
            inspection=InspectionAssessment(status="unknown"),
            ready_for_pricing=False,
        )
        turn = self.turn(
            prior_expert_state=PriorExpertState(
                package_id=package_id,
                package_version=3,
            )
        )

        result = analyze_requirement_turn(
            turn,
            client=self.client_for(self.model_payload()),
            prior_package=prior,
        )

        self.assertEqual(result.requirement_package.package_id, package_id)
        self.assertEqual(result.requirement_package.package_version, 4)

    def test_continuation_without_exact_prior_package_fails_closed(self):
        turn = self.turn(
            prior_expert_state=PriorExpertState(
                package_id=uuid4(),
                package_version=2,
            )
        )
        client = self.client_for(self.model_payload())

        with self.assertRaises(PriorExpertStateError):
            analyze_requirement_turn(turn, client=client)

        client.responses.create.assert_not_called()

    def test_unknown_service_domain_is_rejected(self):
        payload = self.model_payload(domain="invented-service")

        with self.assertRaises(RequirementReasoningValidationError):
            analyze_requirement_turn(
                self.turn(),
                client=self.client_for(payload),
            )

    def test_provider_failure_is_sanitized_and_counted(self):
        client = SimpleNamespace(
            responses=SimpleNamespace(
                create=Mock(
                    side_effect=RuntimeError(
                        "provider-secret-marker"
                    )
                )
            )
        )
        metrics = OperationalMetrics()

        with self.assertRaises(RequirementReasoningUnavailableError) as raised:
            analyze_requirement_turn(
                self.turn(),
                client=client,
                metrics=metrics,
            )

        self.assertNotIn("provider-secret-marker", str(raised.exception))
        snapshot = metrics.snapshot()["model_calls"]
        self.assertEqual(snapshot["calls_total"], 1)
        self.assertEqual(snapshot["failures_total"], 1)


if __name__ == "__main__":
    unittest.main()
