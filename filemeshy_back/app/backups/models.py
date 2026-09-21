"""Modelo de corrida de backup (Ronda 7 -- backups automáticos + verificación).

Un backup automático que nadie verifica no es un backup real: `BackupRun` es
el registro consultable de CADA corrida (éxito/falla/tamaño/dónde quedó),
no solo un cron que corre a las 2 AM y se espera que haya funcionado. Ver
`app/worker/tasks/backups.py` (dónde se escribe) y
`app/backups/router.py::GET /admin/backups` (dónde se consulta).

Vive siempre en el schema `public` (no depende de `tenant_schema_ctx`, ver
`app/worker/db.py::get_worker_db`): un `pg_dump` de la base física completa
respalda TODOS los schemas de golpe (en modo cloud, cada tenant es un schema
de la MISMA base de datos, no una base separada) -- es infraestructura de la
instancia entera, no un dato de negocio de un tenant puntual. Mismo criterio
que `cleanup_temp_files` (bucket único global de MinIO) en
`app/worker/tasks/maintenance.py`.
"""

from sqlalchemy import BigInteger, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base
from app.shared.utils.uuid7 import uuid7


class BackupRun(Base):
    """Una corrida de backup (`'postgres'` o `'minio'`), en cualquiera de sus
    tres estados: `'running'` (recién arrancada, todavía sin resultado),
    `'success'` o `'failed'`.

    `storage_location`: dónde quedó el backup -- la key del objeto en el
    bucket de MinIO (`postgres`) o la URL/bucket del destino S3 externo
    configurado (`minio`). Queda en `NULL` si la corrida falló, o si el
    backup fue exitoso pero el objeto ya se purgó por retención (ver
    `app.worker.tasks.backups.backup_postgres`: la FILA se conserva como
    registro histórico -- solo se borra el objeto real de MinIO y se limpia
    este campo -- decisión de diseño documentada en el docstring de esa
    tarea)."""

    __tablename__ = "backup_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    backup_type = Column(String(20), nullable=False, index=True)  # 'postgres' | 'minio'
    status = Column(String(20), nullable=False)  # 'running' | 'success' | 'failed'

    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    size_bytes = Column(BigInteger, nullable=True)
    storage_location = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
