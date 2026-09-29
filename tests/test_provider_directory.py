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

    def test_area_key_is_explicit_canonical_identifier(self):
        for area_key in (
            "bn:brunei-muara",
            "au:nsw:sydney",
            "postcode:2000",
            "zone:north-1",
        ):
            with self.subTest(area_key=area_key):
                self.assertEqual(
                    provider_directory.validate_area_key(area_key),
                    area_key,
                )

        for area_key in (
            "BN:brunei-muara",
            " bn:brunei-muara",
            "bn:brunei muara",
            "bn/brunei-muara",
            "",
            "x" * 121,
            None,
        ):
            with self.subTest(area_key=area_key):
                with self.assertRaises(ProviderDirectoryValidationError):
                    provider_directory.validate_area_key(area_key)

    def test_invalid_area_key_fails_before_database_access(self):
        with patch.object(provider_directory, "get_connection") as connect:
            with self.assertRaises(ProviderDirectoryValidationError):
                provider_directory.add_provider_coverage_area(
                    "provider-id",
                    "Brunei Muara",
                )
            connect.assert_not_called()

    def test_service_area_lookup_validates_both_inputs_before_database_access(self):
        for service_slug, area_key in (
            ("Plumbing", "bn:brunei-muara"),
            ("plumbing", "BN:brunei-muara"),
        ):
            with self.subTest(service_slug=service_slug, area_key=area_key), patch.object(
                provider_directory, "get_connection"
            ) as connect:
                with self.assertRaises(ProviderDirectoryValidationError):
                    provider_directory.list_approved_providers_for_service_and_area(
                        service_slug,
                        area_key,
                    )
                connect.assert_not_called()

    def test_only_explicit_availability_states_are_accepted(self):
        for status in ("unknown", "available", "unavailable"):
            with self.subTest(status=status):
                self.assertEqual(
                    provider_directory.validate_availability_status(status),
                    status,
                )

        for status in ("busy", "AVAILABLE", "limited", "", None):
            with self.subTest(status=status):
                with self.assertRaises(ProviderDirectoryValidationError):
                    provider_directory.validate_availability_status(status)

    def test_invalid_availability_fails_before_database_access(self):
        with patch.object(provider_directory, "get_connection") as connect:
            with self.assertRaises(ProviderDirectoryValidationError):
                provider_directory.set_provider_availability(
                    "provider-id",
                    "busy",
                )
            connect.assert_not_called()

    def test_available_service_area_lookup_validates_inputs_before_database_access(self):
        for service_slug, area_key in (
            ("Plumbing", "bn:brunei-muara"),
            ("plumbing", "BN:brunei-muara"),
        ):
            with self.subTest(service_slug=service_slug, area_key=area_key), patch.object(
                provider_directory, "get_connection"
            ) as connect:
                with self.assertRaises(ProviderDirectoryValidationError):
                    provider_directory.list_available_approved_providers_for_service_and_area(
                        service_slug,
                        area_key,
                    )
                connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
