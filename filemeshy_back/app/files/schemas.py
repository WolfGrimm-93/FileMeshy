"""Schemas de Carpeta y Archivo para validación y serialización."""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ==================== Breadcrumb ====================

class BreadcrumbItem(BaseModel):
    """Un eslabón de la ruta de ancestros de una carpeta (raíz -> actual)."""
    id: UUID
    name: str


# ==================== Folder ====================

class FolderOut(BaseModel):
    """Respuesta de una carpeta."""
    id: UUID
    name: str
    parent_id: Optional[UUID] = None
    owner_id: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    is_favorite: bool = False

    class Config:
        from_attributes = True


class FolderDetail(FolderOut):
    """Respuesta de `GET /folders/{id}`: metadata + breadcrumb de ancestros."""
    breadcrumb: List[BreadcrumbItem] = Field(default_factory=list)


class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    parent_id: Optional[UUID] = None


class FolderUpdate(BaseModel):
    """Ambos campos opcionales -- el router exige el permiso específico
    (`folders.rename` / `folders.move`) según cuál venga presente."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    parent_id: Optional[UUID] = None
    # Distingue "no tocar parent_id" (campo ausente) de "mover a la raíz"
    # (parent_id=None explícito) -- ver uso de `model_fields_set` en el router.
    is_favorite: Optional[bool] = None
    # Mismo mecanismo (model_fields_set): campo ausente = no tocar, presente
    # (true o false) = valor nuevo.


# ==================== File ====================

class FileOut(BaseModel):
    """Respuesta de un archivo. No expone `storage_key` (detalle interno)."""
    id: UUID
    name: str
    folder_id: Optional[UUID] = None
    owner_id: UUID
    size_bytes: int
    mime_type: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    is_favorite: bool = False

    class Config:
        from_attributes = True


class FileUpdate(BaseModel):
    """Mismo patrón dual de permisos que FolderUpdate."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    folder_id: Optional[UUID] = None
    # Mismo mecanismo de model_fields_set que FolderUpdate.is_favorite.
    is_favorite: Optional[bool] = None


class DownloadUrlResponse(BaseModel):
    download_url: str


class CopyRequest(BaseModel):
    """Body opcional de `POST /files/{id}/copy` y `POST /folders/{id}/copy`.

    `folder_id` es la carpeta destino de la copia. Campo AUSENTE (body vacío
    u omitido) = copiar al mismo lugar que el original (mismo criterio de
    `model_fields_set` que `FileUpdate`/`FolderUpdate`); `folder_id: null`
    explícito = copiar a la raíz; `folder_id: <uuid>` = una carpeta puntual
    (debe pertenecer al mismo dueño del original, ver `_get_target_parent_folder`
    en el router)."""
    folder_id: Optional[UUID] = None


# ==================== Listado de directorio ====================

class DirectoryListing(BaseModel):
    folders: List[FolderOut]
    files: List[FileOut]
    breadcrumb: List[BreadcrumbItem] = Field(default_factory=list)


# ==================== Share (Hito 2: compartir por link) ====================

class ShareCreate(BaseModel):
    expires_at: Optional[datetime] = None


class ShareOut(BaseModel):
    """Respuesta de un share. `is_active` se calcula en el router (no es una
    columna real) -- ver `_share_to_out`."""
    id: UUID
    token: str
    file_id: Optional[UUID] = None
    folder_id: Optional[UUID] = None
    created_by_id: UUID
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


# ==================== Endpoints públicos (sin auth) ====================

class PublicFileShareOut(BaseModel):
    """Respuesta de `GET /public/shares/{token}` cuando el share es de un archivo."""
    type: Literal["file"] = "file"
    name: str
    size_bytes: int
    mime_type: str
    download_url: str


class PublicFolderItem(BaseModel):
    """Subcarpeta dentro de un share de carpeta -- shape mínimo para navegar
    (a diferencia de `FolderOut`, no expone `owner_id`/`deleted_at` a un
    visitante anónimo; hallazgo cosmético de la ronda de feedback de Hito 2,
    2026-09-06)."""
    id: UUID
    name: str

    class Config:
        from_attributes = True


class PublicFileItem(BaseModel):
    """Archivo dentro de un share de carpeta -- shape mínimo para listar y
    descargar (mismo criterio que `PublicFolderItem`)."""
    id: UUID
    name: str
    size_bytes: int
    mime_type: str

    class Config:
        from_attributes = True


class PublicFolderShareOut(BaseModel):
    """Respuesta de `GET /public/shares/{token}` cuando el share es de una
    carpeta -- contenido inmediato de la carpeta compartida (o de la
    subcarpeta indicada por `path`, si es un descendiente real)."""
    type: Literal["folder"] = "folder"
    name: str
    folder_id: UUID
    folders: List[PublicFolderItem]
    files: List[PublicFileItem]


class PublicDownloadResponse(BaseModel):
    download_url: str
