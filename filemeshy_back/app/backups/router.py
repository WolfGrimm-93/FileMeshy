"""Router admin de backups (Ronda 7) -- el registro consultable de cada
corrida (éxito/falla/tamaño) más un disparo manual, para que un admin pueda
verificar que el mecanismo funciona sin esperar al horario (2 AM, ver
`app/worker/celery_app.py::beat_schedule`).

Prefijo fijado en el propio router (mismo criterio que
`admin_configuration_router`, ver `app/api/v1/router.py`)."""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.access_control.service import has_permission
from app.backups.repository import backup_run_repo
from app.backups.schemas import BackupRunListResponse, BackupRunOut, BackupRunTriggerResponse
from app.core.database import get_db
from app.users.models import User

router = APIRouter(prefix="/admin/backups", tags=["admin-backups"])


@router.get("", response_model=BackupRunListResponse)
@router.get("/", response_model=BackupRunListResponse)
def list_backup_runs(
    backup_type: Optional[str] = Query(None, pattern="^(postgres|minio)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["backups.view"])),
):
    """Corridas más recientes primero. `backup_type` filtra opcionalmente
    por `'postgres'`/`'minio'`."""
    items = backup_run_repo.list_recent(db, backup_type=backup_type, skip=skip, limit=limit)
    total = backup_run_repo.count(db, backup_type=backup_type)
    return BackupRunListResponse(items=[BackupRunOut.model_validate(i) for i in items], total=total)


@router.post("/run", response_model=BackupRunTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_manual_backup(
    current_user: User = Depends(has_permission(["backups.view"])),
):
    """Dispara un backup manual de Postgres AHORA, sin esperar al horario
    diario -- así un admin puede confirmar que el mecanismo funciona de
    verdad. Encola vía Celery (`.delay()`), no corre síncrono dentro del
    request -- `pg_dump` puede tardar, y esta ruta no es el lugar para
    bloquear una respuesta HTTP con eso. 202 Accepted (no 200/201): el
    resultado no viaja en esta respuesta, hay que consultarlo después con
    `GET /admin/backups`.

    Import diferido de la tarea -- mismo criterio que
    `_enqueue_content_indexing` en `app/files/router.py`: evita que este
    router (cargado siempre, incluso sin Celery/Redis disponibles en algún
    entorno) dependa a nivel de módulo de que el worker esté importable."""
    from app.worker.tasks.backups import backup_postgres

    backup_postgres.delay()
    return BackupRunTriggerResponse()
