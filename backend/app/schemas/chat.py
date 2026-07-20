from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    filename: str
    page: int
    chunk_index: int


class QueryRequest(BaseModel):
    conversation_id: str
    question: str = Field(min_length=1)


class ConversationResponse(BaseModel):
    id: UUID
    title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    sources: list[SourceCitation] | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}

