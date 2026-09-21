"""Schemas de backups (Ronda 7) para validación y serialización."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class BackupRunOut(BaseModel):
    """Una fila de `GET /admin/backups` -- shape 1:1 con `BackupRun`."""
    id: UUID
    backup_type: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    size_bytes: Optional[int] = None
    storage_location: Optional[str] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class BackupRunListResponse(BaseModel):
    items: List[BackupRunOut]
    total: int


class BackupRunTriggerResponse(BaseModel):
    """Respuesta de `POST /admin/backups/run` -- confirma que el backup de
    Postgres se ENCOLÓ, no que ya terminó (pg_dump corre en el worker, de
    forma asíncrona; el resultado real se consulta después vía
    `GET /admin/backups`)."""
    queued: bool = True
    message: str = "Backup de Postgres encolado"
