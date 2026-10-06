import importlib
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from commercial_contracts import (
    CommercialDurationGuidance,
    CommercialProposalPackage,
)
from expert_commercial_service import (
    CommercialProposalUnavailableError,
    CommercialProposalValidationError,
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


class CommercialProposalApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)

    def payload(self):
        provider_company_id = uuid4()
        requirement_package_id = uuid4()
        return {
            "schema_version": "1.0",
            "correlation_id": "corr-commercial-api-1",
            "idempotency_key": "idem-commercial-api-1",
            "requirement_package": {
                "schema_version": "1.0",
                "package_id": str(requirement_package_id),
                "package_version": 1,
                "domain": "plumbing",
                "customer_objective": "Repair the leaking kitchen tap.",
                "subdomain": None,
                "interpreted_scope": [
                    "Inspect and repair the confirmed leak source."
                ],
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
                    "status": "not_required",
                    "reason": None,
                },
                "environmental_context_constraints": [],
                "dependencies": [],
                "ready_for_pricing": True,
                "confidence_by_section": {},
                "evidence": [],
            },
            "provider_context": {
                "provider_company_id": str(provider_company_id),
                "pricing_policy": "no_estimates",
                "preferred_currency": "AUD",
                "locale": "en-AU",
                "timezone": "Australia/Sydney",
            },
            "business_references": {},
        }

    def result(self, payload):
        requirement = payload["requirement_package"]
        provider = payload["provider_context"]
        return CommercialProposalPackage(
            package_id=uuid4(),
            package_version=1,
            source_requirement_package_id=requirement["package_id"],
            source_requirement_package_version=requirement["package_version"],
            provider_company_id=provider["provider_company_id"],
            pricing_policy=provider["pricing_policy"],
            commercial_summary="Provider-reviewable repair structure.",
            duration_guidance=CommercialDurationGuidance(kind="unknown"),
            ready_for_provider_review=True,
        )

    def test_route_requires_analyze_operator_permission(self):
        response = self.client.post(
            "/v1/expert/commercial-proposals",
            json=self.payload(),
        )
        self.assertEqual(response.status_code, 401)

    def test_route_returns_provider_reviewable_package(self):
        payload = self.payload()
        with patch.object(
            api,
            "analyze_commercial_proposal",
            return_value=self.result(payload),
        ) as analyze:
            response = self.client.post(
                "/v1/expert/commercial-proposals",
                json=payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["provider_review_required"])
        self.assertTrue(body["ready_for_provider_review"])
        self.assertEqual(body["pricing_policy"], "no_estimates")
        analyze.assert_called_once()
        self.assertIs(analyze.call_args.kwargs["client"], api.client)

    def test_policy_validation_maps_to_422(self):
        with patch.object(
            api,
            "analyze_commercial_proposal",
            side_effect=CommercialProposalValidationError(
                "Model returned unsupported commercial value kind"
            ),
        ):
            response = self.client.post(
                "/v1/expert/commercial-proposals",
                json=self.payload(),
                headers={"X-API-Key": OPERATOR_KEY},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            "Model returned unsupported commercial value kind",
        )

    def test_model_unavailability_maps_to_sanitized_502(self):
        with patch.object(
            api,
            "analyze_commercial_proposal",
            side_effect=CommercialProposalUnavailableError(
                "Commercial proposal intelligence is temporarily unavailable"
            ),
        ):
            response = self.client.post(
                "/v1/expert/commercial-proposals",
                json=self.payload(),
                headers={"X-API-Key": OPERATOR_KEY},
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"],
            "Commercial proposal intelligence is temporarily unavailable",
        )


if __name__ == "__main__":
    unittest.main()
