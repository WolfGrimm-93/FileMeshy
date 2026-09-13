"""Modelo de cuota de almacenamiento por usuario.

Tabla separada de `users` (no una columna ahí) para no ensuciar el modelo de
usuario con un contador que se actualiza en cada upload/purge -- misma razón
por la que `Share` vive en su propio módulo en vez de ser una columna de
`files`/`folders`. `bytes_used` es un contador CACHEADO del consumo real en
MinIO (no un reflejo de la papelera): se incrementa al subir un archivo y se
decrementa al purgarlo definitivamente, nunca al soft-delete/restore (ver
app/files/router.py::upload_file y
app/worker/tasks/maintenance.py::purge_deleted_files_and_folders).
"""

from sqlalchemy import Column, BigInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.shared.utils.uuid7 import uuid7


class UserStorageQuota(Base):
    """Límite y consumo de almacenamiento de un usuario.

    `limit_bytes` NULL = sin límite (ilimitado). Una fila por usuario (UNIQUE
    en `user_id`) -- se crea perezosamente en el primer upload/chequeo de
    cuota de ese usuario, no al crear el usuario (la mayoría nunca tendrá un
    límite explícito, no tiene sentido poblar la tabla entera de antemano)."""

    __tablename__ = "user_storage_quotas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    limit_bytes = Column(BigInteger, nullable=True)  # NULL = sin límite
    bytes_used = Column(BigInteger, nullable=False, default=0, server_default="0")

    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id], lazy="select")
