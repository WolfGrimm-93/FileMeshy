"""Schemas de subida multipart (Ronda 9) para validación y serialización."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UploadInitiateRequest(BaseModel):
    file_name: str = Field(..., max_length=255)
    size_bytes: int = Field(..., gt=0)
    mime_type: str = Field(..., max_length=255)
    folder_id: Optional[UUID] = None


class PartUrlOut(BaseModel):
    part_number: int
    url: str


class UploadInitiateResponse(BaseModel):
    upload_session_id: UUID
    part_urls: List[PartUrlOut]
    part_size_bytes: int
    part_count: int
    expires_at: datetime


class CompletedPartOut(BaseModel):
    """Una parte que MinIO confirma como YA subida (`ListParts` real) -- ver
    `POST /uploads/{id}/refresh-part-urls`. El cliente usa esto para saber
    qué partes NO tiene que resubir al reanudar una sesión vieja."""
    part_number: int
    etag: str
    size_bytes: int


class RefreshPartUrlsResponse(BaseModel):
    """URLs presignadas nuevas SOLO para las partes que `ListParts` todavía
    no confirma -- las ya confirmadas viajan en `completed_parts` (con su
    ETag real), no en `part_urls`, así el cliente nunca las resube."""
    part_urls: List[PartUrlOut]
    completed_parts: List[CompletedPartOut]
    expires_at: datetime


class CompletedPartIn(BaseModel):
    part_number: int = Field(..., ge=1)
    etag: str = Field(..., min_length=1)


class UploadCompleteRequest(BaseModel):
    parts: List[CompletedPartIn] = Field(..., min_length=1)


class UploadSessionOut(BaseModel):
    """Estado de una sesión -- respuesta de `abort` y base para diagnósticos.
    Nunca expone `minio_upload_id`/`storage_key`/`last_error` (detalles
    internos, mismo criterio que `FileOut` no expone `storage_key`)."""
    id: UUID
    status: str
    file_name: str
    declared_size_bytes: int
    part_size_bytes: int
    part_count: int
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True
