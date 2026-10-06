import unittest
from uuid import uuid4

from pydantic import ValidationError

from expert_contracts import (
    AgentExecutionContext,
    ExpertProvenance,
    InspectionAssessment,
    RequirementConversationTurn,
    RequirementConversationTurnResponse,
    RequirementEvidence,
    RequirementIntelligencePackage,
    RequirementTurnMessage,
)


class RequirementConversationContractTests(unittest.TestCase):
    def build_turn(self, **overrides):
        payload = {
            "product_surface": "widget",
            "channel": "web",
            "correlation_id": "corr-123",
            "idempotency_key": "turn-123",
            "message": RequirementTurnMessage(
                external_message_id="widget-msg-1",
                external_thread_id="widget-session-1",
                text="My kitchen tap is leaking.",
            ),
            "actor_context": AgentExecutionContext(
                participant_role="customer",
                public_reference="widget-session-1",
            ),
        }
        payload.update(overrides)
        return RequirementConversationTurn(**payload)

    def build_package(self, **overrides):
        payload = {
            "package_id": uuid4(),
            "package_version": 1,
            "domain": "plumbing",
            "customer_objective": "Stop the kitchen tap leak.",
            "interpreted_scope": [
                "Inspect the leaking kitchen tap and identify the cause."
            ],
            "missing_information": [
                "Whether the leak is from the spout, handle, or pipe connection."
            ],
            "clarification_questions": [
                "Where is the water leaking from: the spout, handle, or pipe connection?"
            ],
            "inspection": InspectionAssessment(status="unknown"),
            "ready_for_pricing": False,
            "evidence": [
                RequirementEvidence(
                    kind="supplied_fact",
                    statement="The kitchen tap is leaking.",
                    source_reference="widget-msg-1",
                    confidence=1.0,
                )
            ],
        }
        payload.update(overrides)
        return RequirementIntelligencePackage(**payload)

    def test_minimal_turn_is_valid_and_channel_neutral(self):
        turn = self.build_turn()

        self.assertEqual(turn.schema_version, "1.0")
        self.assertEqual(turn.product_surface, "widget")
        self.assertEqual(turn.channel, "web")
        self.assertEqual(turn.message.external_thread_id, "widget-session-1")
        self.assertIsNone(turn.business_references.service_request_id)
        self.assertIsNone(turn.prior_expert_state)

    def test_unknown_turn_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.build_turn(send_authority=True)

    def test_empty_message_text_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.build_turn(
                message=RequirementTurnMessage(
                    external_message_id="widget-msg-2",
                    text="",
                )
            )

    def test_package_preserves_evidence_semantics(self):
        package = self.build_package()

        self.assertFalse(package.ready_for_pricing)
        self.assertEqual(package.evidence[0].kind, "supplied_fact")
        self.assertEqual(package.inspection.status, "unknown")

    def test_price_fields_are_not_part_of_requirement_package(self):
        with self.assertRaises(ValidationError):
            RequirementIntelligencePackage(
                **self.build_package().model_dump(),
                price=250.00,
                currency="AUD",
            )

    def test_response_can_return_clarification_draft_without_send_authority(self):
        package = self.build_package()
        response = RequirementConversationTurnResponse(
            requirement_package=package,
            directive="ask_clarification",
            clarification_questions=package.clarification_questions,
            reply_draft=(
                "Where is the water leaking from: the spout, handle, "
                "or pipe connection?"
            ),
            provenance=ExpertProvenance(
                analysis_id=uuid4(),
                model="test-model",
                skill_versions={"plumbing": "1.0.0"},
            ),
        )

        self.assertEqual(response.directive, "ask_clarification")
        self.assertFalse(response.requires_human_review)
        self.assertFalse(response.safety_escalated)
        self.assertNotIn("recipient", response.model_dump())
        self.assertNotIn("send", response.model_dump())

    def test_invalid_interaction_directive_is_rejected(self):
        with self.assertRaises(ValidationError):
            RequirementConversationTurnResponse(
                requirement_package=self.build_package(),
                directive="send_quote",
                provenance=ExpertProvenance(
                    analysis_id=uuid4(),
                    model="test-model",
                ),
            )


if __name__ == "__main__":
    unittest.main()
