import unittest
from uuid import uuid4

import tenant_directory as tenants


class TenantDirectoryTests(unittest.TestCase):
    def test_tenant_key_is_canonical_and_bounded(self):
        for value in (
            "",
            "Tenant-A",
            "tenant_a",
            "-tenant",
            "tenant ",
            "a" * 64,
        ):
            with self.subTest(value=value):
                with self.assertRaises(
                    tenants.TenantValidationError
                ):
                    tenants._normalize_tenant_key(value)

        self.assertEqual(
            tenants._normalize_tenant_key("tenant-a1"),
            "tenant-a1",
        )

    def test_tenant_status_transitions_are_explicit(self):
        self.assertEqual(
            tenants.TENANT_TRANSITIONS["pending"],
            frozenset({"active", "closed"}),
        )
        self.assertEqual(
            tenants.TENANT_TRANSITIONS["active"],
            frozenset({"suspended", "closed"}),
        )
        self.assertEqual(
            tenants.TENANT_TRANSITIONS["suspended"],
            frozenset({"active", "closed"}),
        )
        self.assertEqual(
            tenants.TENANT_TRANSITIONS["closed"],
            frozenset(),
        )

    def test_uuid_validation_is_fail_closed(self):
        tenant_id = uuid4()
        self.assertEqual(
            tenants._validate_uuid(tenant_id, "tenant_id"),
            tenant_id,
        )
        with self.assertRaises(tenants.TenantValidationError):
            tenants._validate_uuid(str(tenant_id), "tenant_id")


if __name__ == "__main__":
    unittest.main()
