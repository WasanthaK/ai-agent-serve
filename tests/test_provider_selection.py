import unittest
from uuid import uuid4

from provider_selection import (
    ProviderSelectionValidationError,
    select_providers_for_request,
)


class ProviderSelectionValidationTests(unittest.TestCase):
    def test_selection_requires_at_least_one_provider(self):
        with self.assertRaises(ProviderSelectionValidationError):
            select_providers_for_request(
                uuid4(),
                "plumbing",
                "bn:brunei-muara",
                [],
                actor="operator:test",
            )

    def test_selection_rejects_duplicate_provider_ids(self):
        provider_id = uuid4()
        with self.assertRaises(ProviderSelectionValidationError):
            select_providers_for_request(
                uuid4(),
                "plumbing",
                "bn:brunei-muara",
                [provider_id, provider_id],
                actor="operator:test",
            )

    def test_selection_rejects_noncanonical_service_or_area_before_database_access(self):
        for service_slug, area_key in (
            (" plumbing", "bn:brunei-muara"),
            ("plumbing", "BN:BRUNEI-MUARA"),
        ):
            with self.subTest(service_slug=service_slug, area_key=area_key):
                with self.assertRaises(ProviderSelectionValidationError):
                    select_providers_for_request(
                        uuid4(),
                        service_slug,
                        area_key,
                        [uuid4()],
                        actor="operator:test",
                    )

    def test_selection_requires_a_human_actor(self):
        with self.assertRaises(ProviderSelectionValidationError):
            select_providers_for_request(
                uuid4(),
                "plumbing",
                "bn:brunei-muara",
                [uuid4()],
                actor=" ",
            )


if __name__ == "__main__":
    unittest.main()
