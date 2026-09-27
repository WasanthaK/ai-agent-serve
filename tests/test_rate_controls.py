import json
import os
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

import request_controls
from observability import StructuredRequestLoggingMiddleware


class FakeClock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


class RollingWindowRateLimiterTests(unittest.TestCase):
    def test_exact_limit_is_allowed_then_retry_after_is_returned(self):
        clock = FakeClock(100.0)
        limiter = request_controls.RollingWindowRateLimiter(
            limit=2,
            window_seconds=60,
            clock=clock,
        )

        self.assertIsNone(limiter.check("operator:one"))
        clock.value = 101.0
        self.assertIsNone(limiter.check("operator:one"))
        clock.value = 102.0
        self.assertEqual(limiter.check("operator:one"), 58)

    def test_window_expiry_releases_capacity(self):
        clock = FakeClock(10.0)
        limiter = request_controls.RollingWindowRateLimiter(
            limit=1,
            window_seconds=60,
            clock=clock,
        )

        self.assertIsNone(limiter.check("channel:website"))
        clock.value = 69.9
        self.assertEqual(limiter.check("channel:website"), 1)
        clock.value = 70.0
        self.assertIsNone(limiter.check("channel:website"))

    def test_identities_have_independent_buckets(self):
        limiter = request_controls.RollingWindowRateLimiter(
            limit=1,
            clock=FakeClock(5.0),
        )

        self.assertIsNone(limiter.check("operator:one"))
        self.assertEqual(limiter.check("operator:one"), 60)
        self.assertIsNone(limiter.check("operator:two"))

    def test_invalid_rate_limit_configuration_fails_closed(self):
        for value in ("not-an-int", "0", "-1", "10001"):
            with self.subTest(value=value), patch.dict(
                os.environ,
                {"TEST_RATE_LIMIT": value},
                clear=True,
            ):
                with self.assertRaises(RuntimeError):
                    request_controls.load_rate_limit("TEST_RATE_LIMIT", 60)


class RateLimitHTTPTests(unittest.TestCase):
    def test_429_preserves_correlation_id_and_retry_after(self):
        limiter = request_controls.RollingWindowRateLimiter(
            limit=1,
            clock=FakeClock(100.0),
        )
        app = FastAPI()
        app.add_middleware(StructuredRequestLoggingMiddleware)

        @app.get("/limited")
        async def limited(request: Request):
            retry_after = limiter.check("operator:test")
            if retry_after is not None:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(retry_after)},
                )
            return {"ok": True}

        client = TestClient(app)
        first = client.get("/limited")
        second = client.get("/limited")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json(), {"detail": "Rate limit exceeded"})
        self.assertEqual(second.headers["Retry-After"], "60")
        UUID(second.headers["X-Correlation-ID"])

    def test_security_uses_stable_authenticated_identities_not_keys(self):
        import security

        inbound_key_one = "inbound-one-" + "a" * 40
        inbound_key_two = "inbound-two-" + "b" * 40
        operator_key_one = "operator-one-" + "c" * 40
        operator_key_two = "operator-two-" + "d" * 40
        principal = security.OperatorPrincipal("stable-user", frozenset({"read"}))
        request = MagicMock()
        request.scope = {"route": None}
        request.method = "GET"

        inbound_limiter = MagicMock()
        inbound_limiter.check.side_effect = [None, 30]
        operator_limiter = MagicMock()
        operator_limiter.check.side_effect = [None, 20]

        inbound_digests = (
            security._key_digest(inbound_key_one),
            security._key_digest(inbound_key_two),
        )
        operators = (
            (security._key_digest(operator_key_one), principal),
            (security._key_digest(operator_key_two), principal),
        )

        with patch.object(security, "_INBOUND_DIGESTS", inbound_digests), \
             patch.object(security, "_INBOUND_SOURCE", "website"), \
             patch.object(security, "_INBOUND_LIMITER", inbound_limiter), \
             patch.object(security, "_OPERATORS", operators), \
             patch.object(security, "_OPERATOR_LIMITER", operator_limiter), \
             patch.object(security.security_logger, "warning"):
            self.assertEqual(
                security.require_inbound_key(request, inbound_key_one),
                "website",
            )
            with self.assertRaises(HTTPException) as inbound_error:
                security.require_inbound_key(request, inbound_key_two)

            authenticate = security.require_operator_permission("read")
            self.assertEqual(authenticate(request, operator_key_one), principal)
            with self.assertRaises(HTTPException) as operator_error:
                authenticate(request, operator_key_two)

        self.assertEqual(
            [call.args[0] for call in inbound_limiter.check.call_args_list],
            ["channel:website", "channel:website"],
        )
        self.assertEqual(
            [call.args[0] for call in operator_limiter.check.call_args_list],
            ["operator:stable-user", "operator:stable-user"],
        )
        self.assertEqual(inbound_error.exception.status_code, 429)
        self.assertEqual(inbound_error.exception.headers["Retry-After"], "30")
        self.assertEqual(operator_error.exception.status_code, 429)
        self.assertEqual(operator_error.exception.headers["Retry-After"], "20")


if __name__ == "__main__":
    unittest.main()
