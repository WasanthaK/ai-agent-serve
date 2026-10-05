import json
import os
import unittest
from unittest.mock import patch

import security


INBOUND_KEY = "inbound-" + "a" * 40
OPERATOR_KEY = "operator-" + "b" * 40
ROTATED_INBOUND_KEY = "inbound-new-" + "c" * 40


class TenantAuthContextTests(unittest.TestCase):
    def test_operator_credentials_bind_tenant_key(self):
        entries = [{
            "id": "tenant-admin",
            "key": OPERATOR_KEY,
            "permissions": ["read", "decide"],
            "tenant_key": "tenant-a",
        }]
        with patch.dict(
            os.environ,
            {"AGENT_OPERATOR_CREDENTIALS": json.dumps(entries)},
        ):
            _inbound, operators = security.load_credentials()

        principal = operators[0][1]
        self.assertEqual(principal.id, "tenant-admin")
        self.assertEqual(principal.tenant_key, "tenant-a")

    def test_channel_credentials_bind_tenant_key(self):
        entries = [
            {
                "source": "website",
                "key": INBOUND_KEY,
                "tenant_key": "tenant-a",
            },
            {
                "source": "whatsapp",
                "key": ROTATED_INBOUND_KEY,
                "tenant_key": "tenant-b",
            },
        ]
        with patch.dict(os.environ, {
            "AGENT_INBOUND_API_KEY": "",
            "AGENT_INBOUND_API_KEYS": "",
            "AGENT_INBOUND_SOURCE": "",
            "AGENT_INBOUND_TENANT_KEY": "",
            "AGENT_INBOUND_CREDENTIALS": json.dumps(entries),
        }):
            loaded = security._load_channel_bound_inbound_credentials()

        self.assertEqual(
            [(source, tenant) for _, source, tenant in loaded],
            [("website", "tenant-a"), ("whatsapp", "tenant-b")],
        )

    def test_invalid_tenant_keys_fail_closed(self):
        entries = [{
            "id": "tenant-admin",
            "key": OPERATOR_KEY,
            "permissions": ["read"],
            "tenant_key": "Tenant-A",
        }]
        with patch.dict(
            os.environ,
            {"AGENT_OPERATOR_CREDENTIALS": json.dumps(entries)},
        ):
            with self.assertRaises(RuntimeError):
                security.load_credentials()

    def test_legacy_operator_credentials_remain_unbound(self):
        entries = [{
            "id": "legacy",
            "key": OPERATOR_KEY,
            "permissions": ["read"],
        }]
        with patch.dict(
            os.environ,
            {"AGENT_OPERATOR_CREDENTIALS": json.dumps(entries)},
        ):
            _inbound, operators = security.load_credentials()

        self.assertIsNone(operators[0][1].tenant_key)


if __name__ == "__main__":
    unittest.main()
