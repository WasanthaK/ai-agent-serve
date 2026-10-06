import importlib
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from expert_contracts import (
    ExpertProvenance,
    InspectionAssessment,
    RequirementConversationTurnResponse,
    RequirementIntelligencePackage,
)
from expert_requirement_service import (
    PriorExpertStateError,
    RequirementReasoningUnavailableError,
    RequirementReasoningValidationError,
)


INBOUND_KEY = "inbound-" + "a" * 40
OPERATOR_KEY = "operator-" + "b" * 40
OPERATORS = [
    {
        "id": "wasantha",
        "key": OPERATOR_KEY,
        "permissions": ["read", "analyze", "reply", "decide", "tools"],
    },
]

with patch.dict(
    os.environ,
    {
        "OPENAI_API_KEY": "test-only-key",
        "AGENT_INBOUND_API_KEY": INBOUND_KEY,
        "AGENT_INBOUND_SOURCE": "website",
        "AGENT_OPERATOR_CREDENTIALS": json.dumps(OPERATORS),
    },
):
    api = importlib.import_module("app")


class RequirementApiSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)

    def payload(self, *, with_prior=False):
        package_id = uuid4()
        payload = {
            "turn": {
                "schema_version": "1.0",
                "product_surface": "widget",
                "channel": "web",
                "correlation_id": "corr-api-1",
                "idempotency_key": "idem-api-1",
                "message": {
                    "external_message_id": "widget-msg-1",
                    "external_thread_id": "widget-thread-1",
                    "text": "My kitchen tap is leaking.",
                    "media": [],
                },
                "actor_context": {
                    "participant_role": "customer",
                    "public_reference": "widget-thread-1",
                },
                "business_references": {},
            }
        }
        if with_prior:
            payload["turn"]["prior_expert_state"] = {
                "package_id": str(package_id),
                "package_version": 2,
            }
            payload["prior_requirement_package"] = {
                "schema_version": "1.0",
                "package_id": str(package_id),
                "package_version": 2,
                "domain": "plumbing",
                "customer_objective": "Repair the leaking tap.",
                "interpreted_scope": [],
                "work_packages": [],
                "materials_equipment_concepts": [],
                "labour_concepts": [],
                "known_quantities": [],
                "missing_information": [],
                "clarification_questions": [],
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
                "confidence_by_section": {},
                "evidence": [],
            }
        return payload

    def response(self):
        package = RequirementIntelligencePackage(
            package_id=uuid4(),
            package_version=1,
            domain="plumbing",
            customer_objective="Repair the leaking tap.",
            inspection=InspectionAssessment(status="not_required"),
            ready_for_pricing=True,
        )
        return RequirementConversationTurnResponse(
            requirement_package=package,
            directive="ready_for_pricing",
            provenance=ExpertProvenance(
                analysis_id=uuid4(),
                model="test-model",
                skill_versions={"requirement_intelligence": "1.0.0"},
            ),
        )

    def test_route_requires_analyze_operator_permission(self):
        response = self.client.post(
            "/v1/expert/requirements/turn",
            json=self.payload(),
        )

        self.assertEqual(response.status_code, 401)

    def test_route_returns_validated_expert_response(self):
        with patch.object(
            api,
            "analyze_requirement_turn",
            return_value=self.response(),
        ) as analyze:
            response = self.client.post(
                "/v1/expert/requirements/turn",
                json=self.payload(),
                headers={"X-API-Key": OPERATOR_KEY},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["directive"], "ready_for_pricing")
        self.assertEqual(
            response.json()["requirement_package"]["domain"],
            "plumbing",
        )
        analyze.assert_called_once()
        self.assertIs(analyze.call_args.kwargs["client"], api.client)

    def test_route_forwards_exact_prior_package_for_stateless_continuation(self):
        payload = self.payload(with_prior=True)

        with patch.object(
            api,
            "analyze_requirement_turn",
            return_value=self.response(),
        ) as analyze:
            response = self.client.post(
                "/v1/expert/requirements/turn",
                json=payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )

        self.assertEqual(response.status_code, 200)
        prior = analyze.call_args.kwargs["prior_package"]
        self.assertIsNotNone(prior)
        self.assertEqual(prior.package_version, 2)
        self.assertEqual(
            str(prior.package_id),
            payload["turn"]["prior_expert_state"]["package_id"],
        )

    def test_prior_state_conflict_maps_to_409(self):
        with patch.object(
            api,
            "analyze_requirement_turn",
            side_effect=PriorExpertStateError("Prior package mismatch"),
        ):
            response = self.client.post(
                "/v1/expert/requirements/turn",
                json=self.payload(),
                headers={"X-API-Key": OPERATOR_KEY},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Prior package mismatch")

    def test_expert_validation_error_maps_to_422(self):
        with patch.object(
            api,
            "analyze_requirement_turn",
            side_effect=RequirementReasoningValidationError(
                "Invalid expert evidence"
            ),
        ):
            response = self.client.post(
                "/v1/expert/requirements/turn",
                json=self.payload(),
                headers={"X-API-Key": OPERATOR_KEY},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Invalid expert evidence")

    def test_model_unavailability_maps_to_sanitized_502(self):
        with patch.object(
            api,
            "analyze_requirement_turn",
            side_effect=RequirementReasoningUnavailableError(
                "Requirement intelligence is temporarily unavailable"
            ),
        ):
            response = self.client.post(
                "/v1/expert/requirements/turn",
                json=self.payload(),
                headers={"X-API-Key": OPERATOR_KEY},
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"],
            "Requirement intelligence is temporarily unavailable",
        )


if __name__ == "__main__":
    unittest.main()
