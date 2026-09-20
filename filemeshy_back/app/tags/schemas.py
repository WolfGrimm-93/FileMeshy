"""Schemas de Tag para validación y serialización."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TagOut(BaseModel):
    """Respuesta de una etiqueta -- shape mínimo, usado tanto por `GET /tags`
    como embebido en `FileOut.tags`/`FolderOut.tags` (ver app/files/schemas.py)."""
    id: UUID
    name: str
    color: Optional[str] = None

    class Config:
        from_attributes = True


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    color: Optional[str] = Field(None, max_length=20)


class TagUpdate(BaseModel):
    """Ambos campos opcionales -- se usa `model_fields_set` en el router para
    distinguir "no tocar" (campo ausente) de un valor nuevo explícito (mismo
    mecanismo que `FileUpdate`/`FolderUpdate` en app/files/schemas.py),
    incluido `color: null` explícito para borrar el color actual."""
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    color: Optional[str] = Field(None, max_length=20)
