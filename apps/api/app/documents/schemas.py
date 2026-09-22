from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

TITLE_MAX_LENGTH = 200
FILENAME_MAX_LENGTH = 255


class DocumentCategory(StrEnum):
    ADMINISTRATIVE = "ADMINISTRATIVE"
    CLINICAL = "CLINICAL"


class DocumentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class DocumentListParams(BaseModel):
    category: DocumentCategory | None = None
    status: DocumentStatus = DocumentStatus.ACTIVE
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    patient_id: UUID
    category: DocumentCategory
    title: str
    original_filename: str
    detected_mime: str
    size_bytes: int
    sha256: str
    uploaded_by_user_id: UUID
    status: DocumentStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int
