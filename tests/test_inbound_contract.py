import unittest
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from inbound import (
    InboundAttachment,
    InboundSender,
    NormalizedInboundMessage,
)


class InboundContractTests(unittest.TestCase):
    def test_minimal_message_is_valid(self):
        message = NormalizedInboundMessage(
            channel="website",
            text="My kitchen tap is leaking.",
        )

        self.assertEqual(message.schema_version, "1.0")
        self.assertEqual(message.channel, "website")
        self.assertEqual(message.text, "My kitchen tap is leaking.")
        self.assertEqual(message.attachments, [])
        self.assertIsNone(message.sender)

    def test_full_message_preserves_transport_neutral_envelope(self):
        request_id = uuid4()
        occurred_at = datetime(2026, 9, 29, 4, 30, tzinfo=timezone.utc)

        message = NormalizedInboundMessage(
            channel="whatsapp",
            text="The tap is still leaking.",
            sender=InboundSender(
                external_id="wa-user-123",
                address="+61400000000",
                display_name="Example Customer",
            ),
            external_message_id="wamid.123",
            external_conversation_id="conversation-456",
            occurred_at=occurred_at,
            linked_request_id=request_id,
            attachments=[
                InboundAttachment(
                    reference="attachment-789",
                    media_type="image/jpeg",
                    filename="tap.jpg",
                    size_bytes=1024,
                )
            ],
        )

        self.assertEqual(message.linked_request_id, request_id)
        self.assertEqual(message.occurred_at, occurred_at)
        self.assertEqual(message.sender.display_name, "Example Customer")
        self.assertEqual(message.attachments[0].media_type, "image/jpeg")

    def test_unknown_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            NormalizedInboundMessage(
                channel="email",
                text="Please quote this job.",
                trusted_source="website",
            )

    def test_invalid_channel_and_empty_text_are_rejected(self):
        for payload in (
            {"channel": "Whats App", "text": "Hello"},
            {"channel": "email", "text": ""},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    NormalizedInboundMessage(**payload)

    def test_attachment_count_is_bounded(self):
        attachments = [
            InboundAttachment(
                reference=f"attachment-{index}",
                media_type="text/plain",
            )
            for index in range(21)
        ]

        with self.assertRaises(ValidationError):
            NormalizedInboundMessage(
                channel="email",
                text="See attached files.",
                attachments=attachments,
            )


if __name__ == "__main__":
    unittest.main()
