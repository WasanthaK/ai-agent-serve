import base64
import unittest
from io import BytesIO

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from starlette.datastructures import FormData, Headers, UploadFile

from sendgrid_inbound import (
    SendGridPayloadError,
    build_sendgrid_email_envelope,
    verify_sendgrid_signature,
)


class SendGridInboundTests(unittest.TestCase):
    def setUp(self):
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        public_der = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.public_key_b64 = base64.b64encode(public_der).decode("ascii")

    def _signature(self, timestamp, raw_body):
        signature = self.private_key.sign(
            timestamp.encode("utf-8") + raw_body,
            ec.ECDSA(hashes.SHA256()),
        )
        return base64.b64encode(signature).decode("ascii")

    def test_signature_verification_uses_exact_raw_body(self):
        timestamp = "1790670000"
        raw_body = b"--boundary\r\nraw multipart bytes\r\n--boundary--\r\n"
        signature = self._signature(timestamp, raw_body)

        self.assertTrue(
            verify_sendgrid_signature(
                raw_body=raw_body,
                signature=signature,
                timestamp=timestamp,
                public_key_b64=self.public_key_b64,
            )
        )

        self.assertFalse(
            verify_sendgrid_signature(
                raw_body=raw_body + b"changed",
                signature=signature,
                timestamp=timestamp,
                public_key_b64=self.public_key_b64,
            )
        )

    def test_missing_signature_or_timestamp_is_rejected(self):
        self.assertFalse(
            verify_sendgrid_signature(
                raw_body=b"payload",
                signature=None,
                timestamp="1790670000",
                public_key_b64=self.public_key_b64,
            )
        )
        self.assertFalse(
            verify_sendgrid_signature(
                raw_body=b"payload",
                signature="signature",
                timestamp=None,
                public_key_b64=self.public_key_b64,
            )
        )

    def test_default_parse_payload_maps_to_provider_neutral_email_envelope(self):
        upload = UploadFile(
            file=BytesIO(b"photo"),
            filename="tap.jpg",
            headers=Headers({"content-type": "image/jpeg"}),
            size=5,
        )
        form = FormData(
            [
                ("from", "Example Customer <customer@example.com>"),
                ("subject", "Leaking kitchen tap"),
                ("text", "Please send someone tomorrow."),
                (
                    "headers",
                    "Message-ID: <message-123@example.com>\n"
                    "In-Reply-To: <thread-456@example.com>\n"
                    "Date: Tue, 29 Sep 2026 08:00:00 +0000\n",
                ),
                (
                    "attachment-info",
                    '{"attachment1":{"filename":"tap.jpg","type":"image/jpeg"}}',
                ),
                ("attachment1", upload),
            ]
        )

        envelope = build_sendgrid_email_envelope(form)

        self.assertEqual(envelope.sender_address, "customer@example.com")
        self.assertEqual(envelope.sender_display_name, "Example Customer")
        self.assertEqual(envelope.subject, "Leaking kitchen tap")
        self.assertEqual(envelope.body_text, "Please send someone tomorrow.")
        self.assertEqual(
            envelope.external_message_id,
            "<message-123@example.com>",
        )
        self.assertEqual(
            envelope.external_conversation_id,
            "<thread-456@example.com>",
        )
        self.assertEqual(len(envelope.attachments), 1)
        self.assertEqual(envelope.attachments[0].filename, "tap.jpg")
        self.assertEqual(envelope.attachments[0].media_type, "image/jpeg")
        self.assertEqual(envelope.attachments[0].size_bytes, 5)

    def test_html_body_is_used_when_plain_text_is_absent(self):
        form = FormData(
            [
                ("from", "customer@example.com"),
                ("html", "<p>Please <strong>quote</strong> this job.</p>"),
                ("headers", "Message-ID: <message-html@example.com>\n"),
            ]
        )

        envelope = build_sendgrid_email_envelope(form)
        self.assertEqual(envelope.body_text, "Please quote this job.")

    def test_missing_message_id_gets_stable_derived_identity(self):
        form = FormData(
            [
                ("from", "customer@example.com"),
                ("subject", "Quote"),
                ("text", "Please quote this job."),
                ("headers", "Date: Tue, 29 Sep 2026 08:00:00 +0000\n"),
            ]
        )

        first = build_sendgrid_email_envelope(form)
        second = build_sendgrid_email_envelope(form)

        self.assertTrue(first.external_message_id.startswith("sendgrid-derived:"))
        self.assertEqual(first.external_message_id, second.external_message_id)

    def test_missing_sender_or_body_is_rejected(self):
        with self.assertRaises(SendGridPayloadError):
            build_sendgrid_email_envelope(
                FormData([("text", "No sender")])
            )

        with self.assertRaises(SendGridPayloadError):
            build_sendgrid_email_envelope(
                FormData([("from", "customer@example.com")])
            )


if __name__ == "__main__":
    unittest.main()
