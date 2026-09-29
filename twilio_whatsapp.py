"""Twilio WhatsApp webhook verification and provider translation."""

from urllib.parse import urlparse

from twilio.request_validator import RequestValidator

from inbound import InboundAttachment
from inbound_adapters import WhatsAppInboundEnvelope


TWILIO_SIGNATURE_HEADER = "X-Twilio-Signature"
MAX_MEDIA_ITEMS = 20


class TwilioConfigurationError(Exception):
    """Required Twilio webhook verification configuration is missing or invalid."""


class TwilioWhatsAppPayloadError(Exception):
    """A verified Twilio payload is not a valid inbound WhatsApp message."""


def _required_config(value: str | None, name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise TwilioConfigurationError(f"{name} is not configured")
    return normalized


def validate_public_webhook_url(value: str | None) -> str:
    """Require the exact externally configured HTTPS webhook URL.

    Twilio signs the public URL, not the internal localhost/reverse-proxy URL.
    Keeping this explicit avoids signature failures when the Mac Mini is later
    placed behind a tunnel or reverse proxy.
    """

    url = _required_config(value, "TWILIO_WHATSAPP_WEBHOOK_URL")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise TwilioConfigurationError(
            "TWILIO_WHATSAPP_WEBHOOK_URL must be an absolute HTTPS URL"
        )
    return url


def verify_twilio_signature(
    *,
    webhook_url: str,
    form_params,
    signature: str | None,
    auth_token: str,
) -> bool:
    """Validate an x-www-form-urlencoded Twilio webhook with the SDK."""

    if not signature:
        return False

    token = _required_config(auth_token, "TWILIO_AUTH_TOKEN")
    url = validate_public_webhook_url(webhook_url)
    validator = RequestValidator(token)
    return bool(validator.validate(url, form_params, signature))


def _value(form, name: str) -> str:
    value = form.get(name)
    if value is None:
        return ""
    return str(value).strip()


def _parse_num_media(form) -> int:
    raw = _value(form, "NumMedia") or "0"
    try:
        value = int(raw)
    except ValueError as exc:
        raise TwilioWhatsAppPayloadError("NumMedia must be an integer") from exc

    if value < 0 or value > MAX_MEDIA_ITEMS:
        raise TwilioWhatsAppPayloadError(
            f"NumMedia must be between 0 and {MAX_MEDIA_ITEMS}"
        )
    return value


def _media_attachments(form, count: int) -> list[InboundAttachment]:
    attachments = []
    for index in range(count):
        media_url = _value(form, f"MediaUrl{index}")
        if not media_url:
            raise TwilioWhatsAppPayloadError(
                f"MediaUrl{index} is required when NumMedia includes that item"
            )

        media_type = _value(form, f"MediaContentType{index}")
        attachments.append(
            InboundAttachment(
                reference=media_url,
                media_type=media_type or "application/octet-stream",
            )
        )
    return attachments


def build_twilio_whatsapp_envelope(
    form,
    *,
    expected_account_sid: str,
    expected_sender: str,
    expected_messaging_service_sid: str | None = None,
) -> WhatsAppInboundEnvelope:
    """Translate an already verified Twilio form into the provider-neutral envelope."""

    account_sid = _value(form, "AccountSid")
    if account_sid != _required_config(expected_account_sid, "TWILIO_ACCOUNT_SID"):
        raise TwilioWhatsAppPayloadError("Unexpected Twilio account")

    to_address = _value(form, "To")
    sender = _required_config(expected_sender, "TWILIO_WHATSAPP_SENDER")
    if to_address != sender:
        raise TwilioWhatsAppPayloadError("Unexpected WhatsApp destination")

    expected_service = (expected_messaging_service_sid or "").strip()
    if expected_service:
        service_sid = _value(form, "MessagingServiceSid")
        if service_sid != expected_service:
            raise TwilioWhatsAppPayloadError("Unexpected Twilio Messaging Service")

    message_sid = _value(form, "MessageSid")
    from_address = _value(form, "From")
    wa_id = _value(form, "WaId")
    if not message_sid:
        raise TwilioWhatsAppPayloadError("MessageSid is required")
    if not from_address:
        raise TwilioWhatsAppPayloadError("From is required")

    num_media = _parse_num_media(form)
    attachments = _media_attachments(form, num_media)

    body = _value(form, "Body")
    if not body:
        if attachments:
            body = f"[WhatsApp media message: {len(attachments)} attachment(s)]"
        else:
            raise TwilioWhatsAppPayloadError(
                "Inbound WhatsApp message has neither text nor media"
            )

    sender_external_id = wa_id or from_address
    sender_address = from_address.removeprefix("whatsapp:") or from_address
    profile_name = _value(form, "ProfileName") or None

    return WhatsAppInboundEnvelope(
        sender_external_id=sender_external_id,
        sender_address=sender_address,
        sender_display_name=profile_name,
        body_text=body,
        external_message_id=message_sid,
        attachments=attachments,
    )
