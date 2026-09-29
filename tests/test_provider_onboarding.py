import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import provider_onboarding
from provider_onboarding import ProviderOnboardingValidationError


class ProviderOnboardingContractTests(unittest.TestCase):
    def test_onboarding_statuses_are_explicit(self):
        for status in ("not_started", "in_progress", "submitted", "completed"):
            with self.subTest(status=status):
                self.assertEqual(provider_onboarding.validate_onboarding_status(status), status)

        for status in ("approved", "ready", "COMPLETE", "", None):
            with self.subTest(status=status):
                with self.assertRaises(ProviderOnboardingValidationError):
                    provider_onboarding.validate_onboarding_status(status)

    def test_invalid_expiry_fails_before_database_access(self):
        for expires_at in (
            datetime.now(timezone.utc) - timedelta(minutes=1),
            datetime.now(),
            None,
        ):
            with self.subTest(expires_at=expires_at), patch.object(
                provider_onboarding, "get_connection"
            ) as connect:
                with self.assertRaises(ProviderOnboardingValidationError):
                    provider_onboarding.create_provider_invitation(
                        "provider-id",
                        expires_at,
                    )
                connect.assert_not_called()

    def test_invitation_secret_hash_is_sha256_and_raw_secret_is_not_the_hash(self):
        secret = "one-time-secret"
        digest = provider_onboarding._hash_invitation_secret(secret)

        self.assertEqual(digest, hashlib.sha256(secret.encode("utf-8")).hexdigest())
        self.assertNotEqual(digest, secret)
        self.assertEqual(len(digest), 64)

    def test_invalid_invitation_secret_fails_before_database_access(self):
        for secret in ("", None, "x" * 513):
            with self.subTest(secret=secret), patch.object(
                provider_onboarding, "get_connection"
            ) as connect:
                with self.assertRaises(ProviderOnboardingValidationError):
                    provider_onboarding.accept_provider_invitation(secret)
                connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
