"""Provider-specific SendGrid Inbound Parse verification and translation."""

import base64
import binascii
import hashlib
import json
from datetime import timezone
from email.parser import Parser
from email.policy import default
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from starlette.datastructures import UploadFile

from inbound import InboundAttachment
from inbound_adapters import EmailInboundEnvelope


SENDGRID_SIGNATURE_HEADER = "X-Twilio-Email-Event-Webhook-Signature"
SENDGRID_TIMESTAMP_HEADER = "X-Twilio-Email-Event-Webhook-Timestamp"


class SendGridConfigurationError(Exception):
    """SendGrid verification configuration is absent or malformed."""


class SendGridPayloadError(Exception):
    """A verified SendGrid webhook does not contain a usable email envelope."""


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_data(self, data):
        if data:
            self._parts.append(data)

    def text(self):
        return " ".join(" ".join(self._parts).split())


def _load_public_key(public_key_b64: str):
    value = (public_key_b64 or "").strip()
    if not value:
        raise SendGridConfigurationError(
            "SendGrid inbound verification public key is not configured"
        )

    try:
        key_bytes = base64.b64decode(value, validate=True)
        public_key = serialization.load_der_public_key(key_bytes)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise SendGridConfigurationError(
            "SendGrid inbound verification public key is invalid"
        ) from exc

    if not isinstance(public_key, ec.EllipticCurvePublicKey):
        raise SendGridConfigurationError(
            "SendGrid inbound verification public key must be ECDSA"
        )

    return public_key


def verify_sendgrid_signature(
    *,
    raw_body: bytes,
    signature: str | None,
    timestamp: str | None,
    public_key_b64: str,
) -> bool:
    """Verify SendGrid's ECDSA signature over timestamp + exact raw body."""

    if not signature or not timestamp:
        return False
    if len(signature) > 2048 or len(timestamp) > 100:
        return False

    public_key = _load_public_key(public_key_b64)

    try:
        signature_bytes = base64.b64decode(signature, validate=True)
    except (ValueError, TypeError, binascii.Error):
        return False

    try:
        public_key.verify(
            signature_bytes,
            timestamp.encode("utf-8") + raw_body,
            ec.ECDSA(hashes.SHA256()),
        )
    except InvalidSignature:
        return False

    return True


def _form_string(form, name: str) -> str:
    value = form.get(name)
    if value is None or isinstance(value, UploadFile):
        return ""
    return str(value)


def _parse_email_headers(raw_headers: str):
    if not raw_headers:
        return Parser(policy=default).parsestr("")
    try:
        return Parser(policy=default).parsestr(raw_headers)
    except Exception as exc:
        raise SendGridPayloadError("Email headers could not be parsed") from exc


def _plain_text_body(form) -> str:
    text = _form_string(form, "text").strip()
    if text:
        return text

    html = _form_string(form, "html").strip()
    if html:
        parser = _HTMLTextExtractor()
        parser.feed(html)
        text = parser.text().strip()
        if text:
            return text

    raise SendGridPayloadError("Email has no usable text body")


def _attachment_info(form) -> dict:
    raw_info = _form_string(form, "attachment-info").strip()
    if not raw_info:
        return {}
    try:
        parsed = json.loads(raw_info)
    except ValueError as exc:
        raise SendGridPayloadError("Attachment metadata is invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise SendGridPayloadError("Attachment metadata must be an object")
    return parsed


def _attachment_parts(form, info: dict) -> list[dict]:
    names = set(info)
    if hasattr(form, "multi_items"):
        for name, value in form.multi_items():
            if isinstance(value, UploadFile):
                names.add(name)

    parts = []
    for name in sorted(names):
        metadata = info.get(name) or {}
        if not isinstance(metadata, dict):
            raise SendGridPayloadError("Attachment metadata entry must be an object")

        upload = form.get(name)
        filename = metadata.get("filename") or getattr(upload, "filename", None)
        media_type = metadata.get("type") or getattr(upload, "content_type", None)
        size = getattr(upload, "size", None)
        if size is not None and not isinstance(size, int):
            size = None

        parts.append(
            {
                "part_name": name,
                "filename": filename or None,
                "media_type": media_type or "application/octet-stream",
                "size_bytes": size,
            }
        )

    return parts


def _derived_message_id(
    *,
    raw_headers: str,
    sender: str,
    subject: str,
    body_text: str,
    attachment_parts: list[dict],
) -> str:
    payload = json.dumps(
        {
            "headers": raw_headers,
            "sender": sender,
            "subject": subject,
            "body_text": body_text,
            "attachments": attachment_parts,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sendgrid-derived:{digest}"


def _conversation_id(headers) -> str | None:
    references = headers.get("References")
    if references:
        tokens = references.split()
        if tokens:
            return tokens[0][:500]

    in_reply_to = headers.get("In-Reply-To")
    if in_reply_to:
        return in_reply_to.strip()[:500] or None

    return None


def _occurred_at(headers):
    date_value = headers.get("Date")
    if not date_value:
        return None
    try:
        value = parsedate_to_datetime(date_value)
    except (TypeError, ValueError, OverflowError):
        return None
    if value is not None and value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def build_sendgrid_email_envelope(form) -> EmailInboundEnvelope:
    """Translate a verified SendGrid multipart form into the email contract."""

    sender_value = _form_string(form, "from").strip()
    if not sender_value:
        raise SendGridPayloadError("Email sender is missing")

    display_name, sender_address = parseaddr(sender_value)
    sender_address = sender_address.strip() or sender_value
    display_name = display_name.strip() or None

    subject = _form_string(form, "subject").strip() or None
    body_text = _plain_text_body(form)
    raw_headers = _form_string(form, "headers")
    headers = _parse_email_headers(raw_headers)
    attachment_parts = _attachment_parts(form, _attachment_info(form))

    external_message_id = (headers.get("Message-ID") or "").strip()
    if not external_message_id:
        external_message_id = _derived_message_id(
            raw_headers=raw_headers,
            sender=sender_value,
            subject=subject or "",
            body_text=body_text,
            attachment_parts=attachment_parts,
        )
    if len(external_message_id) > 500:
        raise SendGridPayloadError("Email message identifier is too long")

    attachments = [
        InboundAttachment(
            reference=f"sendgrid:{external_message_id}:{part['part_name']}",
            media_type=part["media_type"],
            filename=part["filename"],
            size_bytes=part["size_bytes"],
        )
        for part in attachment_parts
    ]

    return EmailInboundEnvelope(
        sender_address=sender_address,
        sender_display_name=display_name,
        subject=subject,
        body_text=body_text,
        external_message_id=external_message_id,
        external_conversation_id=_conversation_id(headers),
        occurred_at=_occurred_at(headers),
        attachments=attachments,
    )
