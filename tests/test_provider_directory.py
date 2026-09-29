import unittest
from unittest.mock import patch

import provider_directory
from provider_directory import ProviderDirectoryValidationError


class ProviderDirectoryContractTests(unittest.TestCase):
    def test_display_name_is_trimmed_but_not_otherwise_rewritten(self):
        self.assertEqual(
            provider_directory.normalize_provider_display_name("  Reliable Plumbing Co  "),
            "Reliable Plumbing Co",
        )

    def test_invalid_display_names_fail_before_database_access(self):
        for value in ("", "   ", "x" * 201, None):
            with self.subTest(value=value), patch.object(
                provider_directory, "get_connection"
            ) as connect:
                with self.assertRaises(ProviderDirectoryValidationError):
                    provider_directory.create_provider(value)
                connect.assert_not_called()

    def test_only_explicit_approval_states_are_accepted(self):
        for status in ("pending", "approved", "suspended", "rejected"):
            with self.subTest(status=status):
                self.assertEqual(
                    provider_directory.validate_approval_status(status),
                    status,
                )

        for status in ("active", "verified", "APPROVED", "", None):
            with self.subTest(status=status):
                with self.assertRaises(ProviderDirectoryValidationError):
                    provider_directory.validate_approval_status(status)

    def test_invalid_approval_status_fails_before_database_access(self):
        with patch.object(provider_directory, "get_connection") as connect:
            with self.assertRaises(ProviderDirectoryValidationError):
                provider_directory.create_provider(
                    "Reliable Plumbing Co",
                    approval_status="active",
                )
            connect.assert_not_called()

    def test_approved_directory_is_a_deterministic_status_filter(self):
        approved = [{"display_name": "Approved Provider"}]
        with patch.object(
            provider_directory,
            "list_providers",
            return_value=approved,
        ) as list_providers:
            result = provider_directory.list_approved_providers()

        self.assertEqual(result, approved)
        list_providers.assert_called_once_with(approval_status="approved")

    def test_service_slug_must_match_canonical_service_catalogue(self):
        for slug in ("plumbing", "electrical", "hvac", "cleaning"):
            with self.subTest(slug=slug):
                self.assertEqual(provider_directory.validate_service_slug(slug), slug)

        for slug in ("Plumbing", " plumbing", "plumbing ", "unknown-service", "", None):
            with self.subTest(slug=slug):
                with self.assertRaises(ProviderDirectoryValidationError):
                    provider_directory.validate_service_slug(slug)

    def test_invalid_service_slug_fails_before_database_access(self):
        with patch.object(provider_directory, "get_connection") as connect:
            with self.assertRaises(ProviderDirectoryValidationError):
                provider_directory.add_provider_service_capability(
                    "provider-id",
                    "not-in-catalogue",
                )
            connect.assert_not_called()

    def test_approved_service_lookup_validates_slug_before_database_access(self):
        with patch.object(provider_directory, "get_connection") as connect:
            with self.assertRaises(ProviderDirectoryValidationError):
                provider_directory.list_approved_providers_for_service("Plumbing")
            connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
