import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

import security


WEBSITE_KEY = "website-" + "a" * 40
EMAIL_KEY = "email-" + "b" * 40
OPERATOR_KEY = "operator-" + "c" * 40


def request_for(route_path):
    return SimpleNamespace(
        scope={"route": SimpleNamespace(path=route_path)},
        method="POST",
    )


class ChannelBoundInboundAuthTests(unittest.TestCase):
    def test_channel_bound_configuration_maps_each_key_to_one_source(self):
        credentials = [
            {"source": "website", "key": WEBSITE_KEY},
            {"source": "email", "key": EMAIL_KEY},
        ]
        operators = [
            {"id": "operator", "key": OPERATOR_KEY, "permissions": ["read"]},
        ]

        with patch.dict(
            os.environ,
            {
                "AGENT_INBOUND_CREDENTIALS": json.dumps(credentials),
                "AGENT_INBOUND_API_KEY": "",
                "AGENT_INBOUND_API_KEYS": "",
                "AGENT_INBOUND_SOURCE": "",
                "AGENT_OPERATOR_CREDENTIALS": json.dumps(operators),
            },
        ):
            bindings = security._load_channel_bound_inbound_credentials()
            legacy, loaded_operators = security.load_credentials()

        self.assertEqual(legacy, ())
        self.assertEqual(
            [(source) for _, source in bindings],
            ["website", "email"],
        )
        self.assertEqual(len(loaded_operators), 1)

    def test_channel_bound_configuration_rejects_mixed_legacy_settings(self):
        with patch.dict(
            os.environ,
            {
                "AGENT_INBOUND_CREDENTIALS": json.dumps([
                    {"source": "website", "key": WEBSITE_KEY},
                ]),
                "AGENT_INBOUND_API_KEY": WEBSITE_KEY,
            },
        ):
            with self.assertRaises(RuntimeError):
                security._load_channel_bound_inbound_credentials()

    def test_website_routes_reject_email_credential(self):
        bindings = (
            (security._key_digest(WEBSITE_KEY), "website"),
            (security._key_digest(EMAIL_KEY), "email"),
        )
        request = request_for("/webhook/quote-request")

        with (
            patch.object(security, "_CHANNEL_INBOUND_CREDENTIALS", bindings),
            patch.object(security, "_INBOUND_DIGESTS", ()),
            patch.object(security, "_INBOUND_SOURCE", None),
            patch.object(security._INBOUND_LIMITER, "check", return_value=None),
            patch.object(security.security_logger, "warning"),
        ):
            self.assertEqual(
                security.require_inbound_key(request, WEBSITE_KEY),
                "website",
            )
            with self.assertRaises(HTTPException) as raised:
                security.require_inbound_key(request, EMAIL_KEY)

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.detail, "Channel is not authorized")

    def test_explicit_channel_dependency_rejects_wrong_channel(self):
        bindings = (
            (security._key_digest(WEBSITE_KEY), "website"),
            (security._key_digest(EMAIL_KEY), "email"),
        )
        request = request_for("/future-email-route")
        authenticate_email = security.require_inbound_channel("email")

        with (
            patch.object(security, "_CHANNEL_INBOUND_CREDENTIALS", bindings),
            patch.object(security, "_INBOUND_DIGESTS", ()),
            patch.object(security, "_INBOUND_SOURCE", None),
            patch.object(security._INBOUND_LIMITER, "check", return_value=None),
            patch.object(security.security_logger, "warning"),
        ):
            self.assertEqual(authenticate_email(request, EMAIL_KEY), "email")
            with self.assertRaises(HTTPException) as raised:
                authenticate_email(request, WEBSITE_KEY)

        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
