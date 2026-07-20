from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    page_count: int | None = None
    chunk_count: int | None = None
    error_message: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class DocumentStatusResponse(BaseModel):
    id: UUID
    status: str
    page_count: int | None = None
    chunk_count: int | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}
