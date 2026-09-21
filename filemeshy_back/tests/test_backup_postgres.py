"""Ronda 7 -- backup automático de Postgres + verificación real (no basta con
"corrió sin excepción": se confirma que el objeto EXISTE de verdad en MinIO,
con el tamaño que dice el registro, y que la retención borra objetos viejos
de verdad).

`backup_postgres` se invoca DIRECTO como función Python normal, síncrona, sin
pasar por el broker de Celery real -- mismo patrón que
`tests/test_purge_file_versions_quota.py` para
`purge_deleted_files_and_folders` (no hay endpoint HTTP que espere el
resultado del backup en la misma request; `POST /admin/backups/run` solo lo
ENCOLA, ver `test_backups_endpoints.py`)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.backups.models import BackupRun
from app.core.config import settings
from app.files.service import _ensure_private_bucket, _get_client
from app.shared.utils.uuid7 import uuid7
from app.worker.tasks.backups import backup_postgres


def _latest_run(db_session, backup_type: str) -> BackupRun:
    return (
        db_session.query(BackupRun)
        .filter(BackupRun.backup_type == backup_type)
        .order_by(BackupRun.started_at.desc())
        .first()
    )


def test_backup_postgres_creates_successful_run_with_real_object_in_minio(db_session):
    """pg_dump corre de verdad contra la Postgres real del stack -- sin
    mockear nada. Confirma las tres partes del contrato: (1) `BackupRun`
    queda en 'success' con `size_bytes > 0`, (2) el objeto realmente existe
    en el bucket de MinIO en la key que dice `storage_location`, y (3) el
    tamaño real del objeto en MinIO coincide con `size_bytes` -- una fila
    'success' con un objeto que en realidad no se subió (o se subió trunco)
    sería justo el escenario que esta ronda existe para prevenir."""
    backup_postgres()

    run = _latest_run(db_session, "postgres")
    assert run is not None, "No se registró ninguna corrida de backup_postgres"
    assert run.status == "success", f"Esperaba 'success', quedó '{run.status}': {run.error_message}"
    assert run.error_message is None
    assert run.size_bytes is not None and run.size_bytes > 0
    assert run.storage_location, "Un backup 'success' debe apuntar a dónde quedó guardado"

    client = _get_client()
    assert client is not None, "MinIO debería estar disponible en este stack de test"
    head = client.head_object(Bucket=settings.BACKUP_POSTGRES_BUCKET, Key=run.storage_location)
    assert head["ContentLength"] == run.size_bytes, (
        "El tamaño real del objeto en MinIO no coincide con size_bytes registrado -- "
        "un backup 'success' con un objeto trunco/corrupto es peor que uno marcado 'failed'"
    )


def test_backup_postgres_retention_deletes_old_backup_object(db_session):
    """Simula un backup exitoso de hace más de `BACKUP_RETENTION_DAYS` días
    (fila insertada directo + objeto real subido a MinIO, mismo criterio que
    `_force_deleted_31_days_ago` en test_purge_file_versions_quota.py) y
    confirma que la corrida siguiente de `backup_postgres` lo limpia de
    verdad: el objeto deja de existir en MinIO, y la fila `BackupRun` se
    CONSERVA (registro histórico) pero con `storage_location=None` --
    decisión de diseño documentada en `app/worker/tasks/backups.py::_apply_retention`."""
    client = _get_client()
    assert client is not None
    _ensure_private_bucket(settings.BACKUP_POSTGRES_BUCKET)

    old_key = f"postgres/pytest_old_simulated_{uuid7()}.sql.gz"
    client.put_object(
        Bucket=settings.BACKUP_POSTGRES_BUCKET,
        Key=old_key,
        Body=b"contenido de backup simulado, viejo a proposito",
    )

    old_id = uuid7()
    old_started_at = datetime.now(timezone.utc) - timedelta(days=settings.BACKUP_RETENTION_DAYS + 1)
    db_session.execute(
        text(
            "INSERT INTO backup_runs "
            "(id, backup_type, status, started_at, finished_at, size_bytes, storage_location) "
            "VALUES (:id, 'postgres', 'success', :started_at, :started_at, 42, :key)"
        ),
        {"id": old_id, "started_at": old_started_at, "key": old_key},
    )
    db_session.commit()

    backup_postgres()

    row = db_session.query(BackupRun).filter(BackupRun.id == old_id).first()
    assert row is not None, "La retención no debe borrar la FILA, solo el objeto de MinIO"
    assert row.status == "success", "El status histórico no cambia -- solo se limpia storage_location"
    assert row.storage_location is None

    object_still_exists = True
    try:
        client.head_object(Bucket=settings.BACKUP_POSTGRES_BUCKET, Key=old_key)
    except Exception:
        object_still_exists = False
    assert not object_still_exists, "El objeto viejo debería haber sido eliminado de MinIO por la retención"
