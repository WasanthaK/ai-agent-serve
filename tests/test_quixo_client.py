import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from pydantic import ValidationError

from quixo_client import (
    QuixoAuthenticationError,
    QuixoCallerContext,
    QuixoClient,
    QuixoClientConfig,
    QuixoConfigurationError,
    QuixoContractError,
    QuixoExpertEvidenceAttachment,
    QuixoUnavailableError,
)


class QuixoClientTests(unittest.TestCase):
    def config(self, **overrides):
        values = {
            "base_url": "https://quote.test/",
            "internal_service_key": "k" * 40,
            "timeout_seconds": 2,
            "max_attempts": 2,
        }
        values.update(overrides)
        return QuixoClientConfig(**values)

    def caller(self):
        return QuixoCallerContext(
            product_surface="requestquote",
            buyer_organization_id=uuid4(),
            identity_user_id=uuid4(),
        )

    def context_payload(self, request_id):
        return {
            "schema_version": "1.0",
            "service_request_id": str(request_id),
            "request_version": 3,
            "request_mode": "TeamsBuyer",
            "status": "Pending",
            "source": "marketplace",
            "category": "plumbing",
            "subcategory": "tap-repair",
            "urgency": "Normal",
            "title": "Leaking kitchen tap",
            "description": "Kitchen tap is leaking from the base.",
            "specification_path": "OpenSpec",
            "buyer_organization_id": str(uuid4()),
            "requested_by_identity_user_id": str(uuid4()),
            "contact_presence": {
                "has_name": True,
                "has_email": True,
                "has_phone": False,
            },
            "location": {
                "address": "10 Example Street",
                "suburb": "Colombo",
                "state": "Western",
                "postal_code": "00100",
                "country": "Sri Lanka",
                "latitude": 6.9271,
                "longitude": 79.8612,
            },
        }

    def test_get_context_uses_quixo_internal_key_and_explicit_authority_context(self):
        request_id = uuid4()
        caller = self.caller()

        def handler(request):
            self.assertEqual(request.headers["X-Internal-Key"], "k" * 40)
            self.assertEqual(
                request.headers["X-Expert-Product-Surface"],
                "requestquote",
            )
            self.assertEqual(
                request.headers["X-Correlation-ID"],
                "corr-123",
            )
            self.assertEqual(
                request.url.params["buyer_organization_id"],
                str(caller.buyer_organization_id),
            )
            self.assertEqual(
                request.url.params["identity_user_id"],
                str(caller.identity_user_id),
            )
            self.assertNotIn("X-API-Key", request.headers)
            return httpx.Response(
                200,
                json=self.context_payload(request_id),
            )

        with QuixoClient(
            self.config(),
            transport=httpx.MockTransport(handler),
        ) as client:
            result = client.get_request_expert_context(
                request_id,
                caller=caller,
                correlation_id="corr-123",
            )

        self.assertEqual(result.service_request_id, request_id)
        self.assertEqual(result.request_version, 3)

    def test_context_contract_exposes_contact_presence_not_raw_contact_values(self):
        request_id = uuid4()

        def handler(request):
            payload = self.context_payload(request_id)
            payload["customer_email"] = "should-not-cross-boundary@example.com"
            return httpx.Response(200, json=payload)

        with QuixoClient(
            self.config(),
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(QuixoContractError):
                client.get_request_expert_context(
                    request_id,
                    caller=self.caller(),
                    correlation_id="corr-privacy",
                )

    def test_attach_evidence_uses_idempotency_and_versioned_reference_contract(self):
        request_id = uuid4()
        package_id = uuid4()
        analysis_id = uuid4()
        calls = []

        def handler(request):
            calls.append(request)
            body = __import__("json").loads(request.content)
            self.assertEqual(request.headers["Idempotency-Key"], "idem-1")
            self.assertEqual(
                body["caller_context"]["product_surface"],
                "requestquote",
            )
            self.assertEqual(
                body["evidence"]["package_id"],
                str(package_id),
            )
            return httpx.Response(
                200,
                json={
                    "schema_version": "1.0",
                    "accepted": True,
                    "service_request_id": str(request_id),
                    "package_id": str(package_id),
                    "package_version": 2,
                    "evidence_reference": "expert:req:abc",
                },
            )

        evidence = QuixoExpertEvidenceAttachment(
            package_type="requirement_intelligence",
            package_id=package_id,
            package_version=2,
            source_request_version=3,
            analysis_id=analysis_id,
            model="gpt-5.6",
            skill_versions={"requirement_intelligence": "1.0.0"},
            directive="ready_for_pricing",
            ready_for_pricing=True,
        )

        with QuixoClient(
            self.config(),
            transport=httpx.MockTransport(handler),
        ) as client:
            receipt = client.attach_request_expert_evidence(
                request_id,
                evidence,
                caller=self.caller(),
                correlation_id="corr-evidence",
                idempotency_key="idem-1",
            )

        self.assertEqual(len(calls), 1)
        self.assertTrue(receipt.accepted)
        self.assertEqual(receipt.package_id, package_id)

    def test_retry_is_bounded_for_idempotent_post(self):
        attempts = 0
        sleeps = []

        def handler(request):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(503, json={"error": "temporary"})
            return httpx.Response(
                200,
                json={
                    "schema_version": "1.0",
                    "accepted": True,
                    "service_request_id": str(request_id),
                    "package_id": str(package_id),
                    "package_version": 1,
                    "evidence_reference": "expert:req:retry",
                },
            )

        request_id = uuid4()
        package_id = uuid4()
        evidence = QuixoExpertEvidenceAttachment(
            package_type="requirement_intelligence",
            package_id=package_id,
            package_version=1,
            source_request_version=1,
            analysis_id=uuid4(),
            model="gpt-5.6",
        )

        with QuixoClient(
            self.config(max_attempts=2),
            transport=httpx.MockTransport(handler),
            sleep=sleeps.append,
        ) as client:
            receipt = client.attach_request_expert_evidence(
                request_id,
                evidence,
                caller=self.caller(),
                correlation_id="corr-retry",
                idempotency_key="idem-retry",
            )

        self.assertTrue(receipt.accepted)
        self.assertEqual(attempts, 2)
        self.assertEqual(len(sleeps), 1)

    def test_auth_failure_is_not_retried(self):
        attempts = 0

        def handler(request):
            nonlocal attempts
            attempts += 1
            return httpx.Response(401, json={"error": "bad key"})

        with QuixoClient(
            self.config(max_attempts=3),
            transport=httpx.MockTransport(handler),
            sleep=lambda _: self.fail("auth failures must not back off"),
        ) as client:
            with self.assertRaises(QuixoAuthenticationError):
                client.get_request_expert_context(
                    uuid4(),
                    caller=self.caller(),
                    correlation_id="corr-auth",
                )

        self.assertEqual(attempts, 1)

    def test_bounded_transport_failure_is_sanitized(self):
        attempts = 0

        def handler(request):
            nonlocal attempts
            attempts += 1
            raise httpx.ConnectError(
                "secret-host-detail",
                request=request,
            )

        with QuixoClient(
            self.config(max_attempts=2),
            transport=httpx.MockTransport(handler),
            sleep=lambda _: None,
        ) as client:
            with self.assertRaises(QuixoUnavailableError) as raised:
                client.get_request_expert_context(
                    uuid4(),
                    caller=self.caller(),
                    correlation_id="corr-down",
                )

        self.assertEqual(attempts, 2)
        self.assertNotIn("secret-host-detail", str(raised.exception))

    def test_configuration_fails_closed(self):
        with patch.dict(
            os.environ,
            {
                "QUIXO_QUOTE_BASE_URL": "",
                "QUIXO_INTERNAL_SERVICE_KEY": "",
            },
            clear=False,
        ):
            with self.assertRaises(QuixoConfigurationError):
                QuixoClientConfig.from_env()

    def test_unknown_caller_context_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            QuixoCallerContext(
                product_surface="requestquote",
                tenant_id=uuid4(),
            )


if __name__ == "__main__":
    unittest.main()
