import importlib
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from starlette.requests import Request


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


def http_request():
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/requests/test",
        "headers": [],
    })


class TenantRequestScopeTests(unittest.TestCase):
    def test_request_read_uses_authenticated_tenant_scope(self):
        request_id = uuid4()
        tenant_id = uuid4()
        stored = {"id": request_id, "tenant_id": tenant_id}

        with (
            patch.object(
                api,
                "tenant_id_from_request",
                return_value=tenant_id,
            ),
            patch.object(
                api,
                "get_request",
                return_value=stored,
            ) as get_request,
        ):
            result = api.retrieve_request(request_id, http_request())

        self.assertEqual(result, stored)
        get_request.assert_called_once_with(
            request_id,
            tenant_id=tenant_id,
        )

    def test_cross_tenant_request_is_hidden_as_not_found(self):
        request_id = uuid4()
        tenant_id = uuid4()

        with (
            patch.object(
                api,
                "tenant_id_from_request",
                return_value=tenant_id,
            ),
            patch.object(
                api,
                "get_request",
                return_value=None,
            ) as get_request,
        ):
            with self.assertRaises(HTTPException) as raised:
                api.retrieve_request(request_id, http_request())

        self.assertEqual(raised.exception.status_code, 404)
        get_request.assert_called_once_with(
            request_id,
            tenant_id=tenant_id,
        )


if __name__ == "__main__":
    unittest.main()
