"""Modelos de Carpeta y Archivo (Drive real de FileMeshy -- Hito 1).

Soft-delete vía `deleted_at` (papelera): NULL = activo. El borrado recursivo
de carpetas y la purga automática de la papelera se resuelven en el router y
en un job de Celery futuro (Hito 2), no acá -- este archivo es solo el
esquema de columnas/relaciones.
"""

from sqlalchemy import Column, String, DateTime, BigInteger, ForeignKey, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.shared.utils.uuid7 import uuid7


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

    owner = relationship("User", foreign_keys=[owner_id], lazy="select")
    parent = relationship("Folder", remote_side=[id], foreign_keys=[parent_id], lazy="select")


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

    owner = relationship("User", foreign_keys=[owner_id], lazy="select")
    folder = relationship("Folder", foreign_keys=[folder_id], lazy="select")


class Share(Base):
    """Link de compartir (Hito 2) -- token opaco que da acceso público de
    solo lectura a UN archivo o UNA carpeta (con su subárbol). Exactamente
    uno de `file_id`/`folder_id` debe estar seteado (CHECK a nivel DB, no
    solo validación de aplicación).

    Revocar (`revoked_at`) es soft: la fila se conserva como historial, no se
    borra -- a diferencia del soft-delete de archivos/carpetas que sí puede
    restaurarse, un share revocado es terminal (no hay "des-revocar")."""

    __tablename__ = "shares"
    __table_args__ = (
        CheckConstraint(
            "(file_id IS NOT NULL)::int + (folder_id IS NOT NULL)::int = 1",
            name="ck_share_exactly_one_target",
        ),
        Index("ix_share_file_id", "file_id"),
        Index("ix_share_folder_id", "folder_id"),
        Index("ix_share_created_by_id", "created_by_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=True)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("folders.id", ondelete="CASCADE"), nullable=True)

    token = Column(String(64), nullable=False, unique=True)

    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    file = relationship("File", foreign_keys=[file_id], lazy="select")
    folder = relationship("Folder", foreign_keys=[folder_id], lazy="select")
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="select")
