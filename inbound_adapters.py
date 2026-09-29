from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from inbound import (
    InboundAttachment,
    InboundSender,
    NormalizedInboundMessage,
)


class EmailInboundEnvelope(BaseModel):
    """Provider-neutral email payload accepted only after channel verification."""

    model_config = ConfigDict(extra="forbid")

    sender_address: str = Field(
        min_length=1,
        max_length=1000,
    )
    sender_display_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    subject: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    body_text: str = Field(
        min_length=1,
        max_length=19000,
    )
    external_message_id: str = Field(
        min_length=1,
        max_length=500,
    )
    external_conversation_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    occurred_at: Optional[datetime] = None
    attachments: list[InboundAttachment] = Field(
        default_factory=list,
        max_length=20,
    )


def normalize_website_message(
    *,
    authenticated_channel: str,
    text: str,
) -> NormalizedInboundMessage:
    """Translate an authenticated website delivery into the common inbox contract.

    `authenticated_channel` must come from the channel authentication boundary,
    never from an untrusted normalized payload.
    """

    return NormalizedInboundMessage(
        channel=authenticated_channel,
        text=text,
    )


def normalize_email_message(
    *,
    authenticated_channel: str,
    envelope: EmailInboundEnvelope,
) -> NormalizedInboundMessage:
    """Translate a verified email envelope into the common inbox contract.

    This function does not authenticate a provider webhook. The caller must first
    establish channel authority and pass the server-controlled authenticated
    channel. Raw provider payloads must be verified and translated before they
    become an `EmailInboundEnvelope`.
    """

    if authenticated_channel != "email":
        raise ValueError("Email adapter requires the authenticated email channel")

    text = envelope.body_text
    if envelope.subject is not None:
        text = f"Subject: {envelope.subject}\n\n{envelope.body_text}"

    return NormalizedInboundMessage(
        channel=authenticated_channel,
        text=text,
        sender=InboundSender(
            address=envelope.sender_address,
            display_name=envelope.sender_display_name,
        ),
        external_message_id=envelope.external_message_id,
        external_conversation_id=envelope.external_conversation_id,
        occurred_at=envelope.occurred_at,
        attachments=list(envelope.attachments),
    )
