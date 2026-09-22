"""Modelo de sesión de subida multipart (Ronda 9: coordinación de subida
multipart, sesiones de upload, cuota).

Un archivo de 10-15GB no puede seguir el camino síncrono existente
(`app/files/router.py::upload_file`, `content = await file.read()` completo a
RAM antes de escanear/subir) sin arriesgar tumbar el proceso backend entero --
ver el análisis completo en la instrucción de esta ronda, mismo patrón que
Nextcloud/ownCloud: el navegador sube cada parte DIRECTO a MinIO vía URL
presignada (a través de un proxy de nginx que streamea sin bufferizar, ver
`settings.PUBLIC_STORAGE_PROXY_URL`), los bytes NUNCA tocan la memoria del
proceso backend. `UploadSession` es el registro de ESE flujo: qué multipart
upload real existe en MinIO, cuánta cuota tiene reservada, y en qué estado
está -- necesario para poder reanudar una subida cortada (`refresh-part-urls`,
ver `app/uploads/service.py`) y para poder limpiar sesiones abandonadas
(`app/worker/tasks/uploads.py::cleanup_abandoned_upload_sessions`).

Los uploads chicos (≤100MB, `settings.MAX_UPLOAD_SIZE_MB`) NO pasan por acá --
siguen el camino síncrono existente sin cambios, ver docstring de
`app/files/router.py::upload_file`. Este módulo es exclusivamente el camino
nuevo para archivos grandes.
"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base
from app.shared.utils.uuid7 import uuid7


class UploadSession(Base):
    """Una subida multipart en curso (o ya resuelta) de un archivo grande.

    `status`:
      - `'in_progress'`: multipart real creado en MinIO, esperando que el
        cliente suba partes y llame a `/complete` (o abandonada -- ver la
        tarea periódica de limpieza, que la vence según `expires_at`).
      - `'completed_pending_scan'`: `complete_multipart_upload` real ya
        corrió en MinIO, el `File` ya existe (`file_id` seteado) con
        `File.scan_status='pending'` -- terminal para esta tabla, el resto
        del ciclo de vida (limpio/infectado) lo gobierna el escaneo
        asíncrono de AV (otro módulo, Ronda 9 en paralelo) sobre la fila
        `File`, no sobre esta.
      - `'aborted'`: multipart real abortado en MinIO (`abort_multipart_upload`,
        vía `POST /uploads/{id}/abort` o la limpieza periódica de sesiones
        vencidas), cuota reservada liberada. Terminal.
      - `'failed'`: `complete` se llamó pero algo no cerró de forma segura
        (ej. el cliente declaró un tamaño menor al que realmente subió --
        ver `app/uploads/service.py::complete_upload`, política documentada
        ahí). Terminal, nunca tiene `file_id`.

    `quota_reserved_bytes` NO es un espejo estático de `declared_size_bytes`:
    arranca igual (reserva completa por adelantado, ver
    `app/storage_quota/repository.py::reserve_bytes_or_fail`), pero se AJUSTA
    hacia abajo si el tamaño real subido termina siendo menor al declarado
    (`complete_upload`), y se pone en 0 cuando la reserva se libera del todo
    (abort, o expiración -- ver `release_upload_bytes`). Refleja en todo
    momento cuánta cuota real sigue "comprometida" por esta sesión -- útil
    para auditar sin tener que reconstruir el historial de ajustes.

    `last_error`: diagnóstico best-effort para sesiones `'failed'` -- columna
    agregada más allá de lo estrictamente pedido en el diseño de esta ronda
    (documentado en el reporte final del agente): sin esto, una sesión
    `'failed'` queda sin ningún rastro de POR QUÉ falló, dificultando
    soporte/debugging en producción. Nunca se expone tal cual al cliente
    (ver `UploadSessionOut`), es interno.
    """

    __tablename__ = "upload_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'completed_pending_scan', 'aborted', 'failed')",
            name="ck_upload_session_status",
        ),
        Index("ix_upload_session_owner_id", "owner_id"),
        # Compuesto -- es exactamente el WHERE de la tarea periódica de
        # limpieza (status='in_progress' AND expires_at < now()), ver
        # `app/worker/tasks/uploads.py`.
        Index("ix_upload_session_status_expires", "status", "expires_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    file_name = Column(String(255), nullable=False)
    declared_size_bytes = Column(BigInteger, nullable=False)
    mime_type_declared = Column(String(255), nullable=False)
    # SET NULL (no CASCADE): si la carpeta destino se purga de la papelera
    # mientras esta sesión sigue viva, la sesión no debe desaparecer con
    # ella -- perdería el rastro del multipart real todavía abierto en
    # MinIO. El archivo simplemente termina en la raíz si la sesión se
    # completa después de que su carpeta destino ya no existe.
    target_folder_id = Column(UUID(as_uuid=True), ForeignKey("folders.id", ondelete="SET NULL"), nullable=True)

    storage_key = Column(String(500), nullable=False)
    minio_upload_id = Column(String(500), nullable=False)
    part_size_bytes = Column(BigInteger, nullable=False)
    part_count = Column(Integer, nullable=False)

    status = Column(String(30), nullable=False, server_default="in_progress")
    quota_reserved_bytes = Column(BigInteger, nullable=False)

    # SET NULL: ver docstring de la clase -- un File purgado mucho después no
    # debe arrastrar el registro histórico de cómo se subió.
    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"), nullable=True)

    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
