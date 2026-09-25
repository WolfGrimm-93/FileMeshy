"""Modelos de Carpeta y Archivo (Drive real de FileMeshy -- Hito 1).

Soft-delete vía `deleted_at` (papelera): NULL = activo. El borrado recursivo
de carpetas y la purga automática de la papelera se resuelven en el router y
en un job de Celery futuro (Hito 2), no acá -- este archivo es solo el
esquema de columnas/relaciones.
"""

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    BigInteger,
    Integer,
    Boolean,
    ForeignKey,
    Index,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.shared.utils.uuid7 import uuid7
from app.tags.models import file_tags, folder_tags


class Folder(Base):
    """Carpeta del Drive. Auto-referencial (`parent_id`) -- NULL = raíz."""

    __tablename__ = "folders"
    __table_args__ = (
        Index("ix_folder_parent_id", "parent_id"),
        Index("ix_folder_owner_id", "owner_id"),
        Index("ix_folder_deleted_at", "deleted_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    name = Column(String(255), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("folders.id", ondelete="CASCADE"), nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    is_favorite = Column(Boolean, nullable=False, server_default='false')

    owner = relationship("User", foreign_keys=[owner_id], lazy="select")
    parent = relationship("Folder", remote_side=[id], foreign_keys=[parent_id], lazy="select")
    tags = relationship("Tag", secondary=folder_tags, back_populates="folders", lazy="select")


class File(Base):
    """Archivo del Drive. `storage_key` apunta al bucket privado de MinIO."""

    __tablename__ = "files"
    __table_args__ = (
        Index("ix_file_folder_id", "folder_id"),
        Index("ix_file_owner_id", "owner_id"),
        Index("ix_file_deleted_at", "deleted_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    name = Column(String(255), nullable=False)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("folders.id", ondelete="CASCADE"), nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    storage_key = Column(String(500), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    mime_type = Column(String(255), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    is_favorite = Column(Boolean, nullable=False, server_default='false')

    # Ronda 9 (coordinación de subida multipart + antivirus asíncrono):
    # 'clean' | 'pending' | 'infected' | 'scan_failed'. Default 'clean' -- el
    # camino de upload SÍNCRONO existente (≤ MAX_UPLOAD_SIZE_MB, sin cambios
    # en esta ronda) ya escanea con ClamAV ANTES de crear la fila, así que
    # cualquier File nuevo de ESE camino nace 'clean' sin que su código
    # tenga que setear nada (server_default a nivel de columna, ver la
    # migración de esta ronda). Solo el camino NUEVO de subida multipart
    # (`app/uploads/service.py::complete_upload`) crea filas 'pending' --
    # quedan invisibles/no descargables hasta que el escaneo asíncrono de AV
    # (`app/worker/tasks/av_scan.py`, módulo aparte, construido en paralelo
    # esta misma ronda) las resuelva a 'clean' (limpio confirmado),
    # 'infected' (amenaza real, cuarentena) o 'scan_failed' (reintentos
    # agotados sin poder escanear, ej. clamd caído) -- las CUATRO se filtran
    # de forma centralizada en `app/files/repository.py::CRUDFile`
    # (get/get_active/get_children/get_trash/search/get_by_folder_ids), que
    # solo deja pasar 'clean'.
    scan_status = Column(String(20), nullable=False, server_default='clean')

    owner = relationship("User", foreign_keys=[owner_id], lazy="select")
    folder = relationship("Folder", foreign_keys=[folder_id], lazy="select")
    tags = relationship("Tag", secondary=file_tags, back_populates="files", lazy="select")
    versions = relationship(
        "FileVersion",
        back_populates="file",
        foreign_keys="FileVersion.file_id",
        lazy="select",
        order_by="FileVersion.version_number.desc()",
        # `passive_deletes=True` -- SIN esto, al hacer `db.delete(file_obj)`
        # (purga de papelera) el ORM por defecto intenta poner `file_id=NULL`
        # en cada `FileVersion` hija ANTES de borrar el `File` padre, algo
        # que la columna NOT NULL rechaza (IntegrityError, confirmado en vivo
        # con un smoke test real durante la verificación de Ronda 4: la
        # purga fallaba silenciosamente -- "se continúa" en el log, fila de
        # File NUNCA se borraba). Con `passive_deletes=True`, el ORM no
        # toca las filas hijas y deja que el `ON DELETE CASCADE` real de la
        # FK (ver `FileVersion.file_id`) se encargue solo, tal como se
        # documenta en el docstring de `purge_deleted_files_and_folders`.
        passive_deletes=True,
    )


class FileVersion(Base):
    """Historial de versiones de un `File` (Ronda 4: versionado de archivos).

    `File.storage_key`/`size_bytes`/`mime_type` SIEMPRE reflejan la versión
    más reciente (denormalizado para lecturas rápidas, igual que antes de
    esta ronda) -- `file_versions` es la fuente de verdad del historial
    completo, incluida la versión 1 (la del upload original, creada junto
    con el propio `File` en `upload_file`). Un archivo SIEMPRE tiene al
    menos una versión.

    Cada versión nueva sube un blob NUEVO a MinIO (nunca pisa el anterior) --
    a diferencia del reemplazo de contenido de Ronda 3 (que sí liberaba la
    cuota vieja), acá el blob viejo se conserva como historial real y
    consume cuota real adicional contra el dueño del archivo (ver
    `_create_new_file_version` en el router). Restaurar una versión anterior
    NO sube nada nuevo -- crea una fila de historial que apunta al MISMO
    `storage_key` que la versión restaurada, sin costo de cuota adicional
    (ver `restore_file_version`).

    Sin soft-delete propio: el historial completo de versiones de un
    archivo se borra en cascada (`ON DELETE CASCADE`) cuando el archivo se
    purga definitivamente de la papelera (ver
    `app/worker/tasks/maintenance.py::purge_deleted_files_and_folders`,
    que borra a mano los objetos de MinIO de TODAS las versiones antes de
    dejar que el CASCADE borre las filas)."""

    __tablename__ = "file_versions"
    __table_args__ = (
        UniqueConstraint("file_id", "version_number", name="uq_file_version_number"),
        Index("ix_file_version_file_id", "file_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False)

    storage_key = Column(String(500), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    mime_type = Column(String(255), nullable=False)

    # Quién subió ESTA versión -- puede ser el dueño del archivo o un
    # destinatario de share con permission='edit' (ver
    # `replace_file_via_share`, que reusa `_create_new_file_version` pasando
    # el id del destinatario, no el del dueño).
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    file = relationship("File", back_populates="versions", foreign_keys=[file_id], lazy="select")
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="select")


class FileContentIndex(Base):
    """Índice de contenido extraído de un archivo (Ronda 6: búsqueda por
    contenido + OCR). Relación 1:1 con `File` (`file_id` es PK propia, no
    hay historial por versión -- SIEMPRE refleja el contenido de la versión
    ACTUAL, ver `app/worker/tasks/indexing.py::index_file_content`, que
    hace upsert por `file_id` cada vez que el contenido cambia).

    `content_text` viaja truncado a un límite razonable (ver
    `MAX_CONTENT_CHARS` en la tarea de indexación) -- el propósito de esta
    tabla es habilitar búsqueda full-text, no archivar el documento
    completo.

    NO se mapea acá `search_vector` (la columna generada por Postgres que
    realmente indexa el texto, `GENERATED ALWAYS AS
    to_tsvector('spanish', coalesce(content_text, '')) STORED`, ver la
    migración de esta ronda) -- Postgres rechaza cualquier INSERT/UPDATE
    que intente escribirla explícitamente, y SQLAlchemy no tiene una forma
    limpia de marcar una columna ORM como "generada, nunca la toques al
    persistir" sin recurrir a workarounds frágiles entre versiones. Más
    simple resolverla con SQL crudo (`text()`) donde hace falta consultarla
    -- ver `app/files/repository.py::_content_match_file_ids`, mismo
    criterio que ya usa este módulo para `WITH RECURSIVE` en
    `CRUDFolder.get_descendant_ids`.

    Mientras `extraction_status` sigue en 'pending' (tarea todavía no
    corrió) o directamente no existe fila para un `file_id`, ese archivo
    simplemente no aparece en resultados de búsqueda por CONTENIDO -- sigue
    apareciendo por nombre como siempre. La indexación es asíncrona y best
    effort, nunca bloquea la respuesta de un upload/versión nueva/restore
    (ver `_enqueue_content_indexing` en el router)."""

    __tablename__ = "file_content_index"

    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), primary_key=True)

    content_text = Column(Text, nullable=True)
    # 'pending' | 'done' | 'failed' | 'unsupported'
    extraction_status = Column(String(20), nullable=False, server_default="pending")
    error_message = Column(Text, nullable=True)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    # Intentos de indexación del encolado actual (tope contra redelivery
    # indefinida, ver app/worker/tasks/indexing.py::MAX_INDEX_ATTEMPTS).
    attempts = Column(Integer, nullable=False, server_default="0", default=0)
    # Último inicio de intento (lo pone `register_attempt`); el barrido de
    # filas 'pending' huérfanas (maintenance) lo usa para medir antigüedad.
    attempted_at = Column(DateTime(timezone=True), nullable=True)

    file = relationship("File", foreign_keys=[file_id], lazy="select")


class Share(Base):
    """Link de compartir (Hito 2) -- token opaco que da acceso público de
    solo lectura a UN archivo o UNA carpeta (con su subárbol). Exactamente
    uno de `file_id`/`folder_id` debe estar seteado (CHECK a nivel DB, no
    solo validación de aplicación).

    Revocar (`revoked_at`) es soft: la fila se conserva como historial, no se
    borra -- a diferencia del soft-delete de archivos/carpetas que sí puede
    restaurarse, un share revocado es terminal (no hay "des-revocar").

    Ronda 3 (compartir granular) -- dos modos, no se mezclan:
    - Link público anónimo (`shared_with_user_id IS NULL`, como en Hito 2):
      accedido por `token` sin autenticación. Si tiene `password_hash`, el
      acceso público exige esa contraseña (ver `_verify_share_password` en
      el router). Siempre de solo lectura -- `permission` no aplica acá,
      nadie anónimo puede escribir.
    - Share dirigido a un usuario (`shared_with_user_id IS NOT NULL`):
      acceso SIEMPRE autenticado (nunca por el endpoint público), y
      `permission='edit'` habilita subir/reemplazar contenido (ver
      `/shares/{id}/files` y `/shares/{id}/content` en el router). No
      necesita `token` -- puede ser NULL.

    El CHECK `ck_share_token_or_recipient` exige que un share sea accesible
    por AL MENOS una vía (token o destinatario), nunca los dos NULL a la vez.
    """

    __tablename__ = "shares"
    __table_args__ = (
        CheckConstraint(
            "(file_id IS NOT NULL)::int + (folder_id IS NOT NULL)::int = 1",
            name="ck_share_exactly_one_target",
        ),
        CheckConstraint(
            "(token IS NOT NULL) OR (shared_with_user_id IS NOT NULL)",
            name="ck_share_token_or_recipient",
        ),
        Index("ix_share_file_id", "file_id"),
        Index("ix_share_folder_id", "folder_id"),
        Index("ix_share_created_by_id", "created_by_id"),
        Index("ix_share_shared_with_user_id", "shared_with_user_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=True)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("folders.id", ondelete="CASCADE"), nullable=True)

    token = Column(String(64), nullable=True, unique=True)

    # Contraseña opcional del link público -- bcrypt vía
    # app.core.security.get_password_hash/verify_password (mismo hashing que
    # el login de usuarios). NUNCA se expone en ShareOut, solo `has_password`.
    password_hash = Column(String(255), nullable=True)
    # 'view' (default) o 'edit'. Solo tiene efecto real en un share dirigido
    # (shared_with_user_id NOT NULL) -- ver docstring de la clase.
    permission = Column(String(10), nullable=False, server_default="view")
    shared_with_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)

    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    file = relationship("File", foreign_keys=[file_id], lazy="select")
    folder = relationship("Folder", foreign_keys=[folder_id], lazy="select")
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="select")
    shared_with = relationship("User", foreign_keys=[shared_with_user_id], lazy="select")
