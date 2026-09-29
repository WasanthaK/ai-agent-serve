import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from inbound import InboundAttachment, NormalizedInboundMessage
from inbound_adapters import WhatsAppInboundEnvelope, normalize_whatsapp_message


class WhatsAppInboundAdapterTests(unittest.TestCase):
    def test_minimal_whatsapp_envelope_normalizes_to_common_contract(self):
        envelope = WhatsAppInboundEnvelope(
            sender_external_id="whatsapp:+61412345678",
            body_text="I need a quote for a leaking kitchen tap.",
            external_message_id="SM123",
        )

        normalized = normalize_whatsapp_message(
            authenticated_channel="whatsapp",
            envelope=envelope,
        )

        self.assertIsInstance(normalized, NormalizedInboundMessage)
        self.assertEqual(normalized.channel, "whatsapp")
        self.assertEqual(
            normalized.text,
            "I need a quote for a leaking kitchen tap.",
        )
        self.assertEqual(
            normalized.sender.external_id,
            "whatsapp:+61412345678",
        )
        self.assertEqual(normalized.external_message_id, "SM123")
        self.assertEqual(normalized.attachments, [])

    def test_full_whatsapp_envelope_preserves_transport_neutral_metadata(self):
        occurred_at = datetime(2026, 9, 29, 8, 45, tzinfo=timezone.utc)
        attachment = InboundAttachment(
            reference="media-1",
            media_type="image/jpeg",
            filename="tap.jpg",
            size_bytes=4096,
        )
        envelope = WhatsAppInboundEnvelope(
            sender_external_id="whatsapp:+61412345678",
            sender_address="+61412345678",
            sender_display_name="Example Customer",
            body_text="The tap is leaking from the base.",
            external_message_id="SM123",
            external_conversation_id="conversation-456",
            occurred_at=occurred_at,
            attachments=[attachment],
        )

        normalized = normalize_whatsapp_message(
            authenticated_channel="whatsapp",
            envelope=envelope,
        )

        self.assertEqual(normalized.sender.address, "+61412345678")
        self.assertEqual(normalized.sender.display_name, "Example Customer")
        self.assertEqual(normalized.external_conversation_id, "conversation-456")
        self.assertEqual(normalized.occurred_at, occurred_at)
        self.assertEqual(normalized.attachments, [attachment])

    def test_adapter_rejects_non_whatsapp_authenticated_channel(self):
        envelope = WhatsAppInboundEnvelope(
            sender_external_id="whatsapp:+61412345678",
            body_text="Please quote this job.",
            external_message_id="SM123",
        )

        with self.assertRaises(ValueError):
            normalize_whatsapp_message(
                authenticated_channel="email",
                envelope=envelope,
            )

    def test_unknown_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            WhatsAppInboundEnvelope(
                sender_external_id="whatsapp:+61412345678",
                body_text="Please quote this job.",
                external_message_id="SM123",
                trusted_source="whatsapp",
            )

    def test_required_identity_message_id_and_text_are_bounded(self):
        invalid_payloads = (
            {
                "sender_external_id": "",
                "body_text": "Please quote this job.",
                "external_message_id": "SM123",
            },
            {
                "sender_external_id": "whatsapp:+61412345678",
                "body_text": "",
                "external_message_id": "SM123",
            },
            {
                "sender_external_id": "whatsapp:+61412345678",
                "body_text": "Please quote this job.",
                "external_message_id": "",
            },
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    WhatsAppInboundEnvelope(**payload)

    def test_attachment_count_is_bounded_by_whatsapp_envelope(self):
        attachments = [
            InboundAttachment(
                reference=f"media-{index}",
                media_type="image/jpeg",
            )
            for index in range(21)
        ]

        with self.assertRaises(ValidationError):
            WhatsAppInboundEnvelope(
                sender_external_id="whatsapp:+61412345678",
                body_text="See attached files.",
                external_message_id="SM123",
                attachments=attachments,
            )


if __name__ == "__main__":
    unittest.main()
