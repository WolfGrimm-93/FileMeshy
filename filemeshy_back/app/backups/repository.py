"""CRUD de `BackupRun` -- Ronda 7.

Router-heavy por convención del proyecto (ver tags/storage_quota): esta capa
solo hace queries/statements, la lógica de negocio (correr pg_dump, subir a
MinIO, aplicar retención) vive en `app/worker/tasks/backups.py`.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.backups.models import BackupRun
from app.shared.repository_base import CRUDBase
from app.shared.utils.uuid7 import uuid7


class CRUDBackupRun(CRUDBase[BackupRun, None, None]):
    def create_running(self, db: Session, backup_type: str) -> BackupRun:
        """Registra el ARRANQUE de una corrida, antes de intentar nada --
        así una corrida que cuelga o mata el proceso worker a mitad de
        camino igual queda visible en `GET /admin/backups` como
        `status='running'` en vez de simplemente no existir (un backup que
        nadie ve que falló no es mejor que uno que nunca corrió)."""
        obj = BackupRun(id=uuid7(), backup_type=backup_type, status="running")
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def mark_success(
        self,
        db: Session,
        backup_run: BackupRun,
        *,
        size_bytes: int,
        storage_location: str,
    ) -> BackupRun:
        backup_run.status = "success"
        backup_run.finished_at = datetime.now(timezone.utc)
        backup_run.size_bytes = size_bytes
        backup_run.storage_location = storage_location
        backup_run.error_message = None
        db.add(backup_run)
        db.commit()
        db.refresh(backup_run)
        return backup_run

    def mark_failed(self, db: Session, backup_run: BackupRun, *, error_message: str) -> BackupRun:
        """Nunca el stack trace completo -- mismo criterio que
        `index_file_content` (app/worker/tasks/indexing.py): solo el
        mensaje, truncado."""
        backup_run.status = "failed"
        backup_run.finished_at = datetime.now(timezone.utc)
        backup_run.error_message = error_message[:2000]
        db.add(backup_run)
        db.commit()
        db.refresh(backup_run)
        return backup_run

    def clear_storage_location(self, db: Session, backup_run: BackupRun) -> BackupRun:
        """Retención: el objeto real en MinIO ya se borró -- la fila queda
        como registro histórico (`status='success'` se conserva), pero deja
        de apuntar a un objeto que ya no existe."""
        backup_run.storage_location = None
        db.add(backup_run)
        db.commit()
        db.refresh(backup_run)
        return backup_run

    def list_recent(
        self,
        db: Session,
        *,
        backup_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[BackupRun]:
        query = db.query(BackupRun)
        if backup_type:
            query = query.filter(BackupRun.backup_type == backup_type)
        return query.order_by(BackupRun.started_at.desc()).offset(skip).limit(limit).all()

    def count(self, db: Session, *, backup_type: Optional[str] = None) -> int:
        query = db.query(BackupRun)
        if backup_type:
            query = query.filter(BackupRun.backup_type == backup_type)
        return query.count()

    def get_old_successful_postgres(self, db: Session, *, older_than: datetime) -> List[BackupRun]:
        """Backups de Postgres exitosos, con objeto TODAVÍA en MinIO
        (`storage_location IS NOT NULL` -- uno ya purgado en una corrida
        anterior no vuelve a intentarse), más viejos que `older_than`."""
        return (
            db.query(BackupRun)
            .filter(
                BackupRun.backup_type == "postgres",
                BackupRun.status == "success",
                BackupRun.started_at < older_than,
                BackupRun.storage_location.isnot(None),
            )
            .all()
        )


backup_run_repo = CRUDBackupRun(BackupRun)
