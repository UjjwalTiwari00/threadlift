"""Normalized conversation format.

Every extractor, regardless of platform, must return a Conversation.
This is the contract that keeps the rest of the app platform-agnostic.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["user", "assistant", "system"]


class CodeBlock(BaseModel):
    language: str = ""
    content: str


class Message(BaseModel):
    role: Role
    content: str
    code_blocks: list[CodeBlock] = Field(default_factory=list)


class Conversation(BaseModel):
    platform: str
    title: str = ""
    source_url: str
    extracted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    messages: list[Message]
