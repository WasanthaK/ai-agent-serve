import unittest
from uuid import uuid4

from db import get_connection
from tenant_directory import (
    TenantStateError,
    create_tenant,
    get_tenant,
    get_tenant_by_key,
    get_tenant_events,
    list_tenants,
    set_tenant_status,
)


class TenantDirectoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tenant_ids = []

    def tearDown(self):
        if not self.tenant_ids:
            return
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM platform_tenants WHERE id = ANY(%s)",
                    (self.tenant_ids,),
                )

    def test_tenant_identity_lifecycle_and_audit(self):
        tenant_id = uuid4()
        self.tenant_ids.append(tenant_id)

        created = create_tenant(
            "ci-tenant-a",
            "CI Tenant A",
            tenant_id=tenant_id,
            actor="operator:ci",
        )
        self.assertEqual(created["id"], tenant_id)
        self.assertEqual(created["tenant_key"], "ci-tenant-a")
        self.assertEqual(created["status"], "pending")

        self.assertEqual(
            get_tenant(tenant_id)["display_name"],
            "CI Tenant A",
        )
        self.assertEqual(
            get_tenant_by_key("ci-tenant-a")["id"],
            tenant_id,
        )

        active = set_tenant_status(
            tenant_id,
            "active",
            actor="operator:ci",
            reason="Tenant onboarding approved.",
        )
        self.assertEqual(active["status"], "active")

        suspended = set_tenant_status(
            tenant_id,
            "suspended",
            actor="operator:ci",
            reason="Administrative hold.",
        )
        self.assertEqual(suspended["status"], "suspended")

        reactivated = set_tenant_status(
            tenant_id,
            "active",
            actor="operator:ci",
            reason="Administrative hold cleared.",
        )
        self.assertEqual(reactivated["status"], "active")

        closed = set_tenant_status(
            tenant_id,
            "closed",
            actor="operator:ci",
            reason="Tenant account closed.",
        )
        self.assertEqual(closed["status"], "closed")

        with self.assertRaises(TenantStateError):
            set_tenant_status(
                tenant_id,
                "active",
                actor="operator:ci",
                reason="Closed tenant cannot be reactivated.",
            )

        events = get_tenant_events(tenant_id)
        self.assertEqual(
            [event["event_type"] for event in events],
            [
                "tenant_created",
                "tenant_status_changed",
                "tenant_status_changed",
                "tenant_status_changed",
                "tenant_status_changed",
            ],
        )
        self.assertEqual(
            events[-1]["details"]["new_status"],
            "closed",
        )

        closed_tenants = list_tenants(status="closed")
        self.assertIn(
            tenant_id,
            {tenant["id"] for tenant in closed_tenants},
        )


if __name__ == "__main__":
    unittest.main()
