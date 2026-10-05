import importlib
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException


INBOUND_KEY = "inbound-" + "a" * 40
OPERATOR_KEY = "operator-" + "b" * 40
OPERATORS = [{
    "id": "tenant-reader",
    "key": OPERATOR_KEY,
    "permissions": ["read"],
    "tenant_key": "tenant-a",
}]

with patch.dict(os.environ, {
    "OPENAI_API_KEY": "test-only-key",
    "AGENT_INBOUND_API_KEY": INBOUND_KEY,
    "AGENT_INBOUND_SOURCE": "website",
    "AGENT_OPERATOR_CREDENTIALS": json.dumps(OPERATORS),
}):
    api = importlib.import_module("app")
    security = importlib.import_module("security")


class TenantRequestScopeTests(unittest.TestCase):
    def principal(self):
        return security.OperatorPrincipal(
            "tenant-reader",
            frozenset({"read"}),
            "tenant-a",
        )

    def test_request_scope_uses_authenticated_tenant(self):
        request_id = uuid4()
        tenant_id = uuid4()
        stored = {"id": request_id, "tenant_id": tenant_id}

        with (
            patch.object(
                api,
                "resolve_active_tenant_id",
                return_value=tenant_id,
            ),
            patch.object(
                api,
                "_tenant_scoped_get_request",
                return_value=stored,
            ) as get_request,
        ):
            result = api._require_operator_request_scope(
                request_id,
                self.principal(),
            )

        self.assertEqual(result.id, "tenant-reader")
        get_request.assert_called_once_with(
            request_id,
            tenant_id,
        )

    def test_cross_tenant_request_is_hidden_as_not_found(self):
        request_id = uuid4()
        tenant_id = uuid4()

        with (
            patch.object(
                api,
                "resolve_active_tenant_id",
                return_value=tenant_id,
            ),
            patch.object(
                api,
                "_tenant_scoped_get_request",
                return_value=None,
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                api._require_operator_request_scope(
                    request_id,
                    self.principal(),
                )

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(
            raised.exception.detail,
            "Request not found",
        )


if __name__ == "__main__":
    unittest.main()
