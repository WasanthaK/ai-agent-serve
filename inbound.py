from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InboundSender(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    address: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=1000,
    )
    display_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
    )


class InboundAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str = Field(
        min_length=1,
        max_length=1000,
    )
    media_type: str = Field(
        min_length=1,
        max_length=200,
    )
    filename: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    size_bytes: Optional[int] = Field(
        default=None,
        ge=0,
    )


class NormalizedInboundMessage(BaseModel):
    """Channel-neutral message produced only by a trusted channel adapter."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    channel: str = Field(
        min_length=1,
        max_length=50,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    )
    text: str = Field(
        min_length=1,
        max_length=20000,
    )
    sender: Optional[InboundSender] = None
    external_message_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    external_conversation_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    occurred_at: Optional[datetime] = None
    linked_request_id: Optional[UUID] = None
    attachments: list[InboundAttachment] = Field(
        default_factory=list,
        max_length=20,
    )
