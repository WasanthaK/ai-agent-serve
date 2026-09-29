import unittest

from twilio.request_validator import RequestValidator

from twilio_whatsapp import (
    TwilioConfigurationError,
    TwilioWhatsAppPayloadError,
    build_twilio_whatsapp_envelope,
    validate_public_webhook_url,
    verify_twilio_signature,
)


ACCOUNT_SID = "AC11111111111111111111111111111111"
AUTH_TOKEN = "test-auth-token"
SENDER = "whatsapp:+15673863543"
SERVICE_SID = "MG22222222222222222222222222222222"
WEBHOOK_URL = "https://hooks.quixo.online/webhook/twilio/whatsapp"


class TwilioWhatsAppTests(unittest.TestCase):
    def _form(self, **overrides):
        form = {
            "AccountSid": ACCOUNT_SID,
            "MessagingServiceSid": SERVICE_SID,
            "MessageSid": "SM33333333333333333333333333333333",
            "From": "whatsapp:+61412345678",
            "To": SENDER,
            "WaId": "61412345678",
            "ProfileName": "Example Customer",
            "Body": "Please quote a leaking kitchen tap.",
            "NumMedia": "0",
        }
        form.update(overrides)
        return form

    def test_signature_validation_uses_exact_public_url_and_form_params(self):
        form = self._form()
        signature = RequestValidator(AUTH_TOKEN).compute_signature(
            WEBHOOK_URL,
            form,
        )
        self.assertTrue(
            verify_twilio_signature(
                webhook_url=WEBHOOK_URL,
                form_params=form,
                signature=signature,
                auth_token=AUTH_TOKEN,
            )
        )

        tampered = dict(form)
        tampered["Body"] = "different"
        self.assertFalse(
            verify_twilio_signature(
                webhook_url=WEBHOOK_URL,
                form_params=tampered,
                signature=signature,
                auth_token=AUTH_TOKEN,
            )
        )

    def test_public_webhook_url_must_be_https(self):
        with self.assertRaises(TwilioConfigurationError):
            validate_public_webhook_url("http://localhost:8000/webhook/twilio/whatsapp")

    def test_text_message_maps_to_provider_neutral_envelope(self):
        envelope = build_twilio_whatsapp_envelope(
            self._form(),
            expected_account_sid=ACCOUNT_SID,
            expected_sender=SENDER,
            expected_messaging_service_sid=SERVICE_SID,
        )

        self.assertEqual(envelope.external_message_id, "SM33333333333333333333333333333333")
        self.assertEqual(envelope.sender_external_id, "61412345678")
        self.assertEqual(envelope.sender_address, "+61412345678")
        self.assertEqual(envelope.sender_display_name, "Example Customer")
        self.assertEqual(envelope.body_text, "Please quote a leaking kitchen tap.")

    def test_media_message_creates_bounded_attachment_references(self):
        form = self._form(
            Body="",
            NumMedia="1",
            MediaUrl0="https://api.twilio.com/media/ME123",
            MediaContentType0="image/jpeg",
        )
        envelope = build_twilio_whatsapp_envelope(
            form,
            expected_account_sid=ACCOUNT_SID,
            expected_sender=SENDER,
            expected_messaging_service_sid=SERVICE_SID,
        )

        self.assertIn("1 attachment", envelope.body_text)
        self.assertEqual(len(envelope.attachments), 1)
        self.assertEqual(envelope.attachments[0].media_type, "image/jpeg")

    def test_location_message_is_normalized_to_text(self):
        form = self._form(
            Body="",
            Latitude="37.7879277",
            Longitude="-122.3937508",
            Label="Job site",
            Address="375 Beale St",
        )
        envelope = build_twilio_whatsapp_envelope(
            form,
            expected_account_sid=ACCOUNT_SID,
            expected_sender=SENDER,
            expected_messaging_service_sid=SERVICE_SID,
        )

        self.assertIn("37.7879277, -122.3937508", envelope.body_text)
        self.assertIn("Job site", envelope.body_text)
        self.assertIn("375 Beale St", envelope.body_text)

    def test_wrong_destination_is_rejected(self):
        with self.assertRaises(TwilioWhatsAppPayloadError):
            build_twilio_whatsapp_envelope(
                self._form(To="whatsapp:+10000000000"),
                expected_account_sid=ACCOUNT_SID,
                expected_sender=SENDER,
                expected_messaging_service_sid=SERVICE_SID,
            )

    def test_wrong_messaging_service_is_rejected(self):
        with self.assertRaises(TwilioWhatsAppPayloadError):
            build_twilio_whatsapp_envelope(
                self._form(MessagingServiceSid="MG99999999999999999999999999999999"),
                expected_account_sid=ACCOUNT_SID,
                expected_sender=SENDER,
                expected_messaging_service_sid=SERVICE_SID,
            )


if __name__ == "__main__":
    unittest.main()
