"""Schemas de Carpeta y Archivo para validación y serialización."""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.tags.schemas import TagOut


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
    tags: List[TagOut] = Field(default_factory=list)

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
    # Ronda 9 (subida multipart + antivirus asíncrono): 'clean' | 'pending' |
    # 'infected' | 'scan_failed' (ver docstring de `File.scan_status` en
    # app/files/models.py). SIEMPRE 'clean' en cualquier respuesta que llegue
    # acá por un listado/búsqueda/detalle normal -- el filtro centralizado en
    # `app/files/repository.py::CRUDFile` ya excluye todo lo que no sea
    # 'clean' de esas lecturas. El único lugar donde este campo viaja con un
    # valor DISTINTO de 'clean' es la respuesta de
    # `POST /uploads/{id}/complete` (`app/uploads/router.py`), que devuelve
    # el `File` recién creado tal cual, todavía 'pending' -- así el frontend
    # puede mostrar "procesando" en vez de asumir que ya está listo. Default
    # 'clean' acá solo como red de seguridad (cualquier `File` real siempre
    # trae la columna poblada, `from_attributes=True` la lee directo del
    # ORM).
    scan_status: str = "clean"
    tags: List[TagOut] = Field(default_factory=list)
    # Solo se setea en resultados de `GET /files?q=...` (Ronda 6: búsqueda
    # por contenido + OCR) -- `None` en cualquier otra respuesta que reuse
    # este mismo schema (subida, listado normal, detalle, etc.). Ver
    # `CRUDFile.search` en repository.py, que anota este valor en memoria
    # sobre cada `File` ORM antes de serializar.
    matched_by: Optional[Literal["name", "content", "both"]] = None

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


class PreviewUrlResponse(BaseModel):
    """Respuesta de `GET /files/{id}/preview` (Ronda 5: preview extendido).

    Para tipos ya servibles inline (imagen, PDF, video, audio -- ver
    `INLINE_SAFE_MIME_TYPES`), `preview_url` es la misma URL firmada de
    descarga normal y `mime_type` es el real del archivo. Para documentos
    Office, `preview_url` apunta al PDF convertido/cacheado y `mime_type`
    es siempre `application/pdf` -- el frontend puede embeber la URL igual
    en los dos casos sin ramificar por tipo."""
    preview_url: str
    mime_type: str


class CopyRequest(BaseModel):
    """Body opcional de `POST /files/{id}/copy` y `POST /folders/{id}/copy`.

    `folder_id` es la carpeta destino de la copia. Campo AUSENTE (body vacío
    u omitido) = copiar al mismo lugar que el original (mismo criterio de
    `model_fields_set` que `FileUpdate`/`FolderUpdate`); `folder_id: null`
    explícito = copiar a la raíz; `folder_id: <uuid>` = una carpeta puntual
    (debe pertenecer al mismo dueño del original, ver `_get_target_parent_folder`
    en el router)."""
    folder_id: Optional[UUID] = None
    # Ronda 12b: forma INEQUÍVOCA de pedir la raíz. `folder_id: null` sigue
    # significando raíz (compatibilidad), pero un cliente que serializa "sin valor"
    # como null no puede distinguirlo de "misma carpeta" -- con `to_root: true` la
    # intención es explícita. Contrato:
    #   * omitir `folder_id` y `to_root` (o body vacío/ausente) -> MISMA carpeta del original
    #   * `folder_id: <uuid>` -> esa carpeta
    #   * `to_root: true` (o `folder_id: null` explícito) -> raíz
    # `to_root: true` junto con un `folder_id` no nulo es contradictorio -> 422.
    to_root: bool = False

    @model_validator(mode="after")
    def _check_destination(self):
        if self.to_root and self.folder_id is not None:
            raise ValueError("to_root=true no se puede combinar con un folder_id")
        return self


# ==================== Tags (Ronda 2) ====================

class TagIdsUpdate(BaseModel):
    """Body de `PUT /files/{id}/tags` y `PUT /folders/{id}/tags` --
    REEMPLAZA el set completo de etiquetas del archivo/carpeta (no es
    incremental add/remove). Todos los ids deben pertenecer al usuario
    dueño del archivo/carpeta -- ver `_resolve_owned_tags` en el router."""
    tag_ids: List[UUID] = Field(default_factory=list)


# ==================== Versiones (Ronda 4) ====================

class FileVersionOut(BaseModel):
    """Una entrada del historial de versiones de un archivo (`GET
    /files/{id}/versions`, orden `version_number` desc).

    `created_by_email`/`created_by_name` se resuelven en el router vía la
    relación `FileVersion.created_by` (mismo criterio de enriquecer la
    respuesta que ya usa `_share_to_out(with_resource_info=True)` para
    `shared_by_email` en Ronda 3) -- quedan en `None` si el usuario que
    subió esa versión fue borrado después (no debería pasar, la FK es
    `ondelete=CASCADE`, pero no hace falta que reviente si pasara)."""
    id: UUID
    file_id: UUID
    version_number: int
    size_bytes: int
    mime_type: str
    created_at: datetime
    created_by_id: UUID
    created_by_email: Optional[str] = None
    created_by_name: Optional[str] = None

    class Config:
        from_attributes = True


# ==================== Índice de contenido (Ronda 6) ====================

class FileIndexStatusOut(BaseModel):
    """Respuesta de `GET /files/{id}/index-status` -- estado de la
    extracción de texto/OCR de un archivo (Ronda 6: búsqueda por contenido).
    `'pending'` cubre TANTO "la tarea está encolada/corriendo" COMO "todavía
    no existe ninguna fila de índice para este archivo" -- desde la
    perspectiva del cliente son el mismo estado ("todavía no puedo buscar
    por contenido en este archivo"), no hace falta distinguirlos."""
    status: Literal["pending", "done", "failed", "unsupported"] = "pending"
    indexed_at: Optional[datetime] = None


# ==================== Listado de directorio ====================

class DirectoryListing(BaseModel):
    folders: List[FolderOut]
    files: List[FileOut]
    breadcrumb: List[BreadcrumbItem] = Field(default_factory=list)


# ==================== Share (Hito 2: compartir por link) ====================

class ShareCreate(BaseModel):
    """Body de `POST /files/{id}/shares` y `POST /folders/{id}/shares`.

    Dos modos, determinados por si viene `shared_with_email` (Ronda 3):
    - Ausente -> link público anónimo (comportamiento de Hito 2 sin
      cambios): se genera un `token` opaco; el share es SIEMPRE de solo
      lectura sin importar `permission` (nadie anónimo puede escribir). Si
      viene `password`, protege el acceso público (ver
      `_verify_share_password` en el router).
    - Presente -> share dirigido a ESE usuario (debe existir, 404 "Usuario
      no encontrado" si no); NO se genera `token` (acceso siempre
      autenticado, nunca por el link público) y `permission` sí aplica.

    `password` viaja en texto plano en el request -- se hashea antes de
    guardar (bcrypt, ver `get_password_hash`) y nunca se devuelve ni se
    loguea."""
    expires_at: Optional[datetime] = None
    password: Optional[str] = Field(None, min_length=1, max_length=255)
    permission: Literal["view", "edit"] = "view"
    shared_with_email: Optional[EmailStr] = None


class ShareOut(BaseModel):
    """Respuesta de un share. `is_active` se calcula en el router (no es una
    columna real) -- ver `_share_to_out`. `token` puede ser `None` en un
    share dirigido a un usuario (Ronda 3). `has_password` nunca expone el
    hash, solo si el link público tiene contraseña configurada.

    `resource_name`/`resource_type`/`shared_by_email` son SIEMPRE `None`
    salvo en `GET /shares/with-me` (`_share_to_out(..., with_resource_info=True)`)
    -- ahí sí se resuelven (nombre del archivo/carpeta compartido + email de
    quien lo compartió) porque esa pantalla necesita mostrar algo más que
    UUIDs pelados. Se agregan como opcionales a ESTE mismo schema (en vez de
    uno aparte solo para with-me) para no duplicar los ~10 campos comunes ni
    obligar al frontend a manejar dos tipos de "share" distintos."""
    id: UUID
    token: Optional[str] = None
    file_id: Optional[UUID] = None
    folder_id: Optional[UUID] = None
    created_by_id: UUID
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime
    is_active: bool
    permission: Literal["view", "edit"] = "view"
    has_password: bool = False
    resource_name: Optional[str] = None
    resource_type: Optional[Literal["file", "folder"]] = None
    shared_by_email: Optional[str] = None
    shared_with_user_id: Optional[UUID] = None
    shared_with_email: Optional[str] = None

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
