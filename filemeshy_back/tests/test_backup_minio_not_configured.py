"""Ronda 7 -- backup de MinIO a destino S3 externo, CONDICIONAL.

Un backup de TODO el contenido de MinIO en el mismo disco/servidor no
protege contra una falla de disco real -- por diseño, `backup_minio_objects`
solo actúa si hay un destino S3-compatible EXTERNO configurado
(`settings.BACKUP_S3_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY`, las 4). Este
stack de test (`docker-compose.yml`) NO define esas variables a propósito --
exactamente el escenario que más importa cubrir: sin config, la tarea tiene
que fallar LIMPIO (un `BackupRun` con motivo explícito), nunca una excepción
sin controlar que reviente el worker, y nunca fingir que se hizo un backup
que no ocurrió."""

from app.backups.models import BackupRun
from app.core.config import settings
from app.worker.tasks.backups import backup_minio_objects


def test_backup_s3_external_not_configured_in_this_stack():
    """Precondición del test -- si algún día este stack de dev/test
    empieza a definir las 4 variables, este test (y el que sigue) dejan de
    tener sentido tal cual están escritos y hay que revisarlos."""
    assert not all(
        [
            settings.BACKUP_S3_ENDPOINT,
            settings.BACKUP_S3_BUCKET,
            settings.BACKUP_S3_ACCESS_KEY,
            settings.BACKUP_S3_SECRET_KEY,
        ]
    )


def test_backup_minio_objects_fails_cleanly_without_external_destination(db_session):
    """Corre `backup_minio_objects` directo (sin broker, mismo criterio que
    `backup_postgres` en test_backup_postgres.py) y confirma: registra un
    `BackupRun(backup_type='minio', status='failed')` con un mensaje CLARO
    (no un stack trace ni un mensaje genérico), y no propaga ninguna
    excepción -- la función tiene que retornar normalmente."""
    backup_minio_objects()  # no debe lanzar

    run = (
        db_session.query(BackupRun)
        .filter(BackupRun.backup_type == "minio")
        .order_by(BackupRun.started_at.desc())
        .first()
    )

    assert run is not None, "backup_minio_objects debe registrar la corrida aunque falle"
    assert run.status == "failed"
    assert run.error_message is not None
    assert "S3 externo" in run.error_message
    assert run.storage_location is None
    assert run.size_bytes is None
