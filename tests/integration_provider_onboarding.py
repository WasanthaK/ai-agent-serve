import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from db import get_connection
from provider_directory import create_provider, get_provider, get_provider_compliance
from provider_onboarding import (
    ProviderInvitationInvalidError,
    accept_provider_invitation,
    advance_provider_onboarding,
    create_provider_invitation,
    get_provider_onboarding,
)


class ProviderOnboardingIntegrationTests(unittest.TestCase):
    def test_invitation_acceptance_and_onboarding_do_not_grant_provider_authority(self):
        provider_id = uuid4()
        create_provider(
            "CI Invited Provider",
            approval_status="pending",
            provider_id=provider_id,
        )

        try:
            created = create_provider_invitation(
                provider_id,
                datetime.now(timezone.utc) + timedelta(hours=1),
            )
            invitation = created["invitation"]
            secret = created["secret"]

            self.assertEqual(invitation["invitation_status"], "pending")
            self.assertEqual(
                get_provider_onboarding(provider_id)["onboarding_status"],
                "not_started",
            )

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT token_hash FROM provider_invitations WHERE id = %s",
                        (invitation["id"],),
                    )
                    token_hash = cur.fetchone()[0]
            self.assertEqual(
                token_hash,
                hashlib.sha256(secret.encode("utf-8")).hexdigest(),
            )
            self.assertNotEqual(token_hash, secret)

            accepted = accept_provider_invitation(secret)
            self.assertEqual(
                accepted["invitation"]["invitation_status"],
                "accepted",
            )
            self.assertEqual(
                accepted["onboarding"]["onboarding_status"],
                "in_progress",
            )

            repeated = accept_provider_invitation(secret)
            self.assertEqual(
                repeated["onboarding"]["onboarding_status"],
                "in_progress",
            )

            submitted = advance_provider_onboarding(provider_id, "submitted")
            completed = advance_provider_onboarding(provider_id, "completed")
            self.assertEqual(submitted["onboarding_status"], "submitted")
            self.assertEqual(completed["onboarding_status"], "completed")

            provider = get_provider(provider_id)
            self.assertEqual(provider["approval_status"], "pending")
            self.assertIsNone(get_provider_compliance(provider_id))
        finally:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM providers WHERE id = %s", (provider_id,))

    def test_expired_invitation_is_durably_expired_and_can_be_replaced(self):
        provider_id = uuid4()
        create_provider(
            "CI Expired Invitation Provider",
            approval_status="pending",
            provider_id=provider_id,
        )

        try:
            created = create_provider_invitation(
                provider_id,
                datetime.now(timezone.utc) + timedelta(hours=1),
            )
            invitation_id = created["invitation"]["id"]
            secret = created["secret"]

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE provider_invitations
                        SET expires_at = NOW() - INTERVAL '1 minute'
                        WHERE id = %s
                        """,
                        (invitation_id,),
                    )

            with self.assertRaises(ProviderInvitationInvalidError):
                accept_provider_invitation(secret)

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT invitation_status FROM provider_invitations WHERE id = %s",
                        (invitation_id,),
                    )
                    self.assertEqual(cur.fetchone()[0], "expired")

            replacement = create_provider_invitation(
                provider_id,
                datetime.now(timezone.utc) + timedelta(hours=1),
            )
            self.assertEqual(
                replacement["invitation"]["invitation_status"],
                "pending",
            )
        finally:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM providers WHERE id = %s", (provider_id,))


if __name__ == "__main__":
    unittest.main()
