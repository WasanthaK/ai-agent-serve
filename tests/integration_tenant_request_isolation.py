import unittest
from uuid import uuid4

from db import get_connection, get_request, save_request
from idempotency import reserve_webhook_delivery
from inbound import NormalizedInboundMessage
from inbound_persistence import (
    InboundMessageLinkConflictError,
    get_inbound_message,
    link_inbound_message_to_request,
    save_inbound_message,
)
from tenant_directory import create_tenant, set_tenant_status


ANALYSIS = {
    "intent": "Request a quote",
    "category": "Plumbing",
    "summary": "Tenant isolation CI request",
    "urgency": "normal",
    "next_action": "Proceed",
    "needs_human_review": False,
    "missing_information": [],
    "follow_up_questions": [],
}


class TenantRequestIsolationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tenant_ids = []
        self.request_ids = []
        self.inbound_ids = []

    def tearDown(self):
        with get_connection() as conn:
            with conn.cursor() as cur:
                if self.inbound_ids:
                    cur.execute(
                        "DELETE FROM inbound_messages WHERE id = ANY(%s)",
                        (self.inbound_ids,),
                    )
                if self.request_ids:
                    cur.execute(
                        "DELETE FROM webhook_idempotency WHERE request_id = ANY(%s)",
                        (self.request_ids,),
                    )
                    cur.execute(
                        "DELETE FROM agent_requests WHERE id = ANY(%s)",
                        (self.request_ids,),
                    )
                if self.tenant_ids:
                    cur.execute(
                        "DELETE FROM platform_tenants WHERE id = ANY(%s)",
                        (self.tenant_ids,),
                    )

    def create_active_tenant(self, key):
        tenant_id = uuid4()
        self.tenant_ids.append(tenant_id)
        create_tenant(
            key,
            f"CI {key}",
            tenant_id=tenant_id,
            actor="operator:ci",
        )
        set_tenant_status(
            tenant_id,
            "active",
            actor="operator:ci",
            reason="Tenant isolation integration proof.",
        )
        return tenant_id

    def test_request_and_inbound_identity_are_tenant_scoped(self):
        tenant_a = self.create_active_tenant("ci-tenant-a")
        tenant_b = self.create_active_tenant("ci-tenant-b")

        request_a = save_request(
            "website",
            "Tenant A Customer",
            "Need plumbing work",
            dict(ANALYSIS),
            tenant_id=tenant_a,
        )
        request_b = save_request(
            "website",
            "Tenant B Customer",
            "Need plumbing work",
            dict(ANALYSIS),
            tenant_id=tenant_b,
        )
        self.request_ids.extend([request_a, request_b])

        self.assertEqual(
            get_request(request_a, tenant_id=tenant_a)["id"],
            request_a,
        )
        self.assertIsNone(
            get_request(request_a, tenant_id=tenant_b)
        )
        self.assertIsNone(
            get_request(request_a, tenant_id=None)
        )

        message = NormalizedInboundMessage(
            channel="website",
            text="Same provider identity across tenants",
            external_message_id="shared-external-id",
        )
        inbound_a = save_inbound_message(
            message,
            tenant_id=tenant_a,
        )
        inbound_b = save_inbound_message(
            message,
            tenant_id=tenant_b,
        )
        inbound_a_id = inbound_a["message"]["id"]
        inbound_b_id = inbound_b["message"]["id"]
        self.inbound_ids.extend([inbound_a_id, inbound_b_id])

        self.assertNotEqual(inbound_a_id, inbound_b_id)
        self.assertEqual(
            get_inbound_message(
                inbound_a_id,
                tenant_id=tenant_a,
            )["id"],
            inbound_a_id,
        )
        self.assertIsNone(
            get_inbound_message(
                inbound_a_id,
                tenant_id=tenant_b,
            )
        )

        link_inbound_message_to_request(
            inbound_a_id,
            request_a,
            tenant_id=tenant_a,
        )
        with self.assertRaises(InboundMessageLinkConflictError):
            link_inbound_message_to_request(
                inbound_b_id,
                request_a,
                tenant_id=tenant_b,
            )

    def test_idempotency_identity_is_tenant_scoped(self):
        tenant_a = self.create_active_tenant("ci-idem-a")
        tenant_b = self.create_active_tenant("ci-idem-b")

        first = reserve_webhook_delivery(
            "website",
            "same-key-hash",
            "same-payload-hash",
            tenant_id=tenant_a,
        )
        second = reserve_webhook_delivery(
            "website",
            "same-key-hash",
            "same-payload-hash",
            tenant_id=tenant_b,
        )
        self.request_ids.extend([
            first["request_id"],
            second["request_id"],
        ])

        self.assertEqual(first["action"], "process")
        self.assertEqual(second["action"], "process")
        self.assertNotEqual(
            first["request_id"],
            second["request_id"],
        )


if __name__ == "__main__":
    unittest.main()
