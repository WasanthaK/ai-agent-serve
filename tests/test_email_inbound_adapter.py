import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from inbound import InboundAttachment, NormalizedInboundMessage
from inbound_adapters import EmailInboundEnvelope, normalize_email_message


class EmailInboundAdapterTests(unittest.TestCase):
    def test_minimal_email_envelope_normalizes_to_common_contract(self):
        envelope = EmailInboundEnvelope(
            sender_address="customer@example.com",
            body_text="Please quote a leaking kitchen tap.",
            external_message_id="message-123",
        )

        normalized = normalize_email_message(
            authenticated_channel="email",
            envelope=envelope,
        )

        self.assertIsInstance(normalized, NormalizedInboundMessage)
        self.assertEqual(normalized.channel, "email")
        self.assertEqual(
            normalized.text,
            "Please quote a leaking kitchen tap.",
        )
        self.assertEqual(normalized.sender.address, "customer@example.com")
        self.assertEqual(normalized.external_message_id, "message-123")
        self.assertEqual(normalized.attachments, [])

    def test_full_email_envelope_preserves_transport_neutral_metadata(self):
        occurred_at = datetime(2026, 9, 29, 7, 45, tzinfo=timezone.utc)
        attachment = InboundAttachment(
            reference="attachment-456",
            media_type="image/jpeg",
            filename="tap.jpg",
            size_bytes=2048,
        )
        envelope = EmailInboundEnvelope(
            sender_address="customer@example.com",
            sender_display_name="Example Customer",
            subject="Leaking kitchen tap",
            body_text="Please send someone tomorrow.",
            external_message_id="message-123",
            external_conversation_id="thread-789",
            occurred_at=occurred_at,
            attachments=[attachment],
        )

        normalized = normalize_email_message(
            authenticated_channel="email",
            envelope=envelope,
        )

        self.assertEqual(
            normalized.text,
            "Subject: Leaking kitchen tap\n\nPlease send someone tomorrow.",
        )
        self.assertEqual(normalized.sender.display_name, "Example Customer")
        self.assertEqual(normalized.external_conversation_id, "thread-789")
        self.assertEqual(normalized.occurred_at, occurred_at)
        self.assertEqual(normalized.attachments, [attachment])

    def test_adapter_rejects_non_email_authenticated_channel(self):
        envelope = EmailInboundEnvelope(
            sender_address="customer@example.com",
            body_text="Please quote this job.",
            external_message_id="message-123",
        )

        with self.assertRaises(ValueError):
            normalize_email_message(
                authenticated_channel="website",
                envelope=envelope,
            )

    def test_unknown_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            EmailInboundEnvelope(
                sender_address="customer@example.com",
                body_text="Please quote this job.",
                external_message_id="message-123",
                trusted_source="email",
            )

    def test_required_email_identity_and_text_are_bounded(self):
        invalid_payloads = (
            {
                "sender_address": "",
                "body_text": "Please quote this job.",
                "external_message_id": "message-123",
            },
            {
                "sender_address": "customer@example.com",
                "body_text": "",
                "external_message_id": "message-123",
            },
            {
                "sender_address": "customer@example.com",
                "body_text": "Please quote this job.",
                "external_message_id": "",
            },
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    EmailInboundEnvelope(**payload)

    def test_attachment_count_is_bounded_by_email_envelope(self):
        attachments = [
            InboundAttachment(
                reference=f"attachment-{index}",
                media_type="text/plain",
            )
            for index in range(21)
        ]

        with self.assertRaises(ValidationError):
            EmailInboundEnvelope(
                sender_address="customer@example.com",
                body_text="See attached files.",
                external_message_id="message-123",
                attachments=attachments,
            )


if __name__ == "__main__":
    unittest.main()
