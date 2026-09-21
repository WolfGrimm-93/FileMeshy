"""Backups automáticos + verificación real -- FileMeshy Worker (Ronda 7).

Un backup automático que nadie verifica no es un backup real. Por eso el
diseño de esta ronda no es "correr un cron y esperar que funcione": cada
corrida (éxito, falla o en curso) queda registrada en `backup_runs`
(`app.backups.models.BackupRun`), consultable vía `GET /admin/backups`
(`app/backups/router.py`) y disparable a demanda vía
`POST /admin/backups/run` -- para que un admin pueda confirmar que el
mecanismo funciona de verdad sin esperar al horario diario.

Dos tareas, con alcance MUY distinto a propósito:

- `backup_postgres`: la base de datos completa (schema, todos los tenants en
  modo cloud -- son schemas de la MISMA base física, un solo `pg_dump`
  alcanza) es chica comparada con el storage de archivos, así que
  automatizarla bien (retención + verificación) es barato y siempre corre.

- `backup_minio_objects`: un backup de TODO el contenido de MinIO
  (`filemeshy-media` + `filemeshy-media-private`) sería caro (duplica el
  storage completo) y, si el destino fuera el MISMO disco/servidor, NO
  protegería contra una falla de disco real -- daría una falsa sensación de
  seguridad. Por diseño, esta tarea SOLO actúa si hay un destino
  S3-compatible EXTERNO configurado (`settings.BACKUP_S3_*`, las 4
  variables). Si falta cualquiera, se registra como 'failed' con el motivo
  explícito y listo -- limitación conocida, documentada en PENDIENTES.md,
  nunca fingida como "ya hay backup de archivos".

Ninguna de las dos tareas revienta el worker -- cualquier excepción (pg_dump
falla, MinIO no responde, credenciales del destino externo inválidas, etc.)
se captura y se persiste como `BackupRun.status='failed'` con el mensaje
(nunca el stack trace completo, mismo criterio que
`app/worker/tasks/indexing.py::index_file_content`)."""

import gzip
import logging
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Tuple
from urllib.parse import urlparse

from app.worker.celery_app import celery_app
from app.worker.db import get_worker_db

logger = logging.getLogger(__name__)

# Timeout de pg_dump -- techo defensivo (mismo criterio que
# TASK_TIME_LIMIT_SECONDS en indexing.py): la BD de este proyecto es chica
# (ver docstring del módulo), 10 minutos es de sobra incluso con margen
# amplio; sin esto, un pg_dump colgado (ej. lock inesperado) dejaría la
# tarea de Celery corriendo para siempre.
PG_DUMP_TIMEOUT_SECONDS = 600


def _parse_database_url(url: str) -> dict:
    """Desarma `DATABASE_URL` (`postgresql://user:pass@host:port/db`) en las
    piezas que necesita la CLI de `pg_dump` -- se pasa la contraseña por
    `PGPASSWORD` (variable de entorno del subproceso), nunca como argumento
    de línea de comandos (evita que quede visible en `ps aux`/logs del
    proceso)."""
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "",
        "password": parsed.password or "",
        "dbname": (parsed.path or "").lstrip("/"),
    }


def _run_pg_dump(db_conn: dict) -> bytes:
    """SQL plano (formato default de `pg_dump`, sin `--format=custom`) --
    criterio "lo más simple de restaurar después": reimportar es
    `gunzip archivo.sql.gz | psql ...`, sin depender de `pg_restore` ni de
    que la versión de `pg_dump` que generó el backup sea compatible con la
    que eventualmente lo restaure (el formato custom es un binario propio de
    Postgres, versionado aparte)."""
    cmd = [
        "pg_dump",
        "--host", db_conn["host"],
        "--port", db_conn["port"],
        "--username", db_conn["user"],
        "--no-password",
        "--dbname", db_conn["dbname"],
    ]
    result = subprocess.run(
        cmd,
        env={"PGPASSWORD": db_conn["password"]},
        capture_output=True,
        timeout=PG_DUMP_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"pg_dump falló (code={result.returncode}): {stderr}")
    if not result.stdout:
        raise RuntimeError("pg_dump no produjo salida (dump vacío)")
    return result.stdout


def _backup_minio_client():
    """Cliente boto3 contra el MinIO INTERNO del stack (donde vive
    `filemeshy-backups`) -- reusa `_get_client()`/`_ensure_private_bucket()`
    de `app.files.service`, mismo mecanismo que ya usa el resto del proyecto
    para no duplicar la config de conexión."""
    from app.files.service import _get_client

    client = _get_client()
    if not client:
        raise RuntimeError("El servicio de almacenamiento (MinIO) no está disponible")
    return client


def _upload_postgres_backup(key: str, content: bytes) -> None:
    from app.core.config import settings
    from app.files.service import _ensure_private_bucket

    client = _backup_minio_client()
    bucket = settings.BACKUP_POSTGRES_BUCKET
    _ensure_private_bucket(bucket)
    client.put_object(Bucket=bucket, Key=key, Body=content, ContentType="application/gzip")


def _delete_postgres_backup(key: str) -> None:
    from app.core.config import settings

    client = _backup_minio_client()
    client.delete_object(Bucket=settings.BACKUP_POSTGRES_BUCKET, Key=key)


def _apply_retention(db) -> None:
    """Después de un backup exitoso, borra los backups de Postgres más
    viejos que `settings.BACKUP_RETENTION_DAYS`. Se borra el OBJETO real en
    MinIO -- la fila `BackupRun` se conserva como registro histórico
    (auditable: "hubo un backup tal día, duró tanto, pesaba tanto"), solo se
    limpia `storage_location` para reflejar que el archivo ya no existe (a
    diferencia de, por ejemplo, `purge_deleted_files_and_folders` en
    maintenance.py, que sí borra la fila entera -- ahí el historial no tiene
    valor de auditoría propio, acá sí: es el registro de que el mecanismo de
    backup viene funcionando).

    Un fallo borrando UN backup viejo no aborta el resto del batch (mismo
    criterio que `purge_deleted_files_and_folders`: un objeto huérfano en
    MinIO es preferible a que una corrida de retención se caiga entera)."""
    from app.backups.repository import backup_run_repo
    from app.core.config import settings

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.BACKUP_RETENTION_DAYS)
    old_runs = backup_run_repo.get_old_successful_postgres(db, older_than=cutoff)

    for run in old_runs:
        try:
            _delete_postgres_backup(run.storage_location)
            backup_run_repo.clear_storage_location(db, run)
            logger.info(f"backup_postgres retention: eliminado backup {run.id} ({run.started_at})")
        except Exception:
            db.rollback()
            logger.exception(f"backup_postgres retention: fallo eliminando backup {run.id}, se continúa")


@celery_app.task(name="app.worker.tasks.backups.backup_postgres", bind=True, max_retries=0)
def backup_postgres(self):
    """Backup completo de Postgres: `pg_dump` -> gzip -> sube a MinIO
    (`settings.BACKUP_POSTGRES_BUCKET`, key `postgres/{timestamp}.sql.gz`) ->
    registra la corrida en `backup_runs` -> aplica retención. Ejecuta
    diariamente a las 2:00 AM (ver `app/worker/celery_app.py::beat_schedule`,
    antes de las tareas de limpieza que corren a las 3-4 AM) y bajo demanda
    vía `POST /admin/backups/run`.

    `max_retries=0` a propósito -- mismo criterio que `index_file_content`:
    un reintento automático inmediato de un `pg_dump` que ya falló (ej.
    Postgres caído, credenciales inválidas) no cambia el resultado; si algún
    día se agrega retry real, debería tener backoff, no un reintento
    inmediato de Celery."""
    from app.backups.repository import backup_run_repo
    from app.core.config import settings

    with get_worker_db(schema_name=None) as db:
        backup_run = backup_run_repo.create_running(db, "postgres")
        try:
            db_conn = _parse_database_url(settings.DATABASE_URL)
            raw_sql = _run_pg_dump(db_conn)
            compressed = gzip.compress(raw_sql, compresslevel=6)

            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            key = f"postgres/{timestamp}.sql.gz"
            _upload_postgres_backup(key, compressed)

            backup_run_repo.mark_success(
                db, backup_run, size_bytes=len(compressed), storage_location=key
            )
            logger.info(
                f"backup_postgres: OK -> {settings.BACKUP_POSTGRES_BUCKET}/{key} "
                f"({len(compressed)} bytes comprimidos)"
            )

            _apply_retention(db)
        except Exception as e:
            logger.exception("backup_postgres: fallo")
            db.rollback()
            backup_run_repo.mark_failed(db, backup_run, error_message=str(e))


def _external_s3_client(settings):
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.BACKUP_S3_ENDPOINT,
        aws_access_key_id=settings.BACKUP_S3_ACCESS_KEY,
        aws_secret_access_key=settings.BACKUP_S3_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def _object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def _sync_bucket_to_external(source_client, dest_client, *, source_bucket: str, dest_bucket: str, dest_prefix: str) -> Tuple[int, int]:
    """Copia a `dest_bucket` (bajo `dest_prefix`, para no mezclar en un único
    bucket destino los objetos de `filemeshy-media` y
    `filemeshy-media-private`) los objetos de `source_bucket` que todavía NO
    existen ahí. Primera versión funcional a propósito -- `list_objects_v2` +
    `get_object`/`put_object` de lo que falte, sin mirror incremental
    sofisticado (sin borrar del destino lo que se borró del origen, sin
    detectar contenido modificado con mismo nombre) -- alcanza para esta
    ronda; no hace falta ser exhaustivo (ver diseño acordado)."""
    total_bytes = 0
    total_objects = 0
    continuation_token = None

    while True:
        kwargs = {"Bucket": source_bucket}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        response = source_client.list_objects_v2(**kwargs)

        for obj in response.get("Contents", []):
            key = obj["Key"]
            dest_key = f"{dest_prefix}/{key}"
            if _object_exists(dest_client, dest_bucket, dest_key):
                continue
            body = source_client.get_object(Bucket=source_bucket, Key=key)["Body"].read()
            dest_client.put_object(Bucket=dest_bucket, Key=dest_key, Body=body)
            total_bytes += len(body)
            total_objects += 1

        if not response.get("IsTruncated"):
            break
        continuation_token = response.get("NextContinuationToken")

    return total_bytes, total_objects


def _sync_buckets_to_external(settings) -> Tuple[int, int]:
    from app.files.service import _get_client

    source_client = _get_client()
    if not source_client:
        raise RuntimeError("El servicio de almacenamiento (MinIO interno) no está disponible")
    dest_client = _external_s3_client(settings)

    total_bytes = 0
    total_objects = 0
    # (bucket real de MinIO, prefijo dentro del bucket externo) -- ambos
    # buckets reales del proyecto, ver app/core/config.py.
    for source_bucket, dest_prefix in (
        (settings.MINIO_BUCKET, "media"),
        (settings.MINIO_PRIVATE_BUCKET, "media-private"),
    ):
        b, o = _sync_bucket_to_external(
            source_client,
            dest_client,
            source_bucket=source_bucket,
            dest_bucket=settings.BACKUP_S3_BUCKET,
            dest_prefix=dest_prefix,
        )
        total_bytes += b
        total_objects += o

    return total_bytes, total_objects


@celery_app.task(name="app.worker.tasks.backups.backup_minio_objects", bind=True, max_retries=0)
def backup_minio_objects(self):
    """Backup de los objetos de MinIO hacia un destino S3-compatible
    EXTERNO -- SOLO si `settings.BACKUP_S3_ENDPOINT/BUCKET/ACCESS_KEY/
    SECRET_KEY` están las 4 configuradas. Si falta cualquiera, se registra
    la corrida como 'failed' con el motivo explícito y se termina ahí, sin
    intentar nada más -- ver docstring del módulo para el razonamiento
    completo (por qué NO hay un backup "por defecto" de MinIO en el mismo
    disco/servidor)."""
    from app.backups.repository import backup_run_repo
    from app.core.config import settings

    required = (
        settings.BACKUP_S3_ENDPOINT,
        settings.BACKUP_S3_BUCKET,
        settings.BACKUP_S3_ACCESS_KEY,
        settings.BACKUP_S3_SECRET_KEY,
    )

    with get_worker_db(schema_name=None) as db:
        backup_run = backup_run_repo.create_running(db, "minio")

        if not all(required):
            backup_run_repo.mark_failed(
                db,
                backup_run,
                error_message="Backup de MinIO no configurado: falta destino S3 externo",
            )
            logger.warning(
                "backup_minio_objects: destino S3 externo no configurado "
                "(BACKUP_S3_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY), omitiendo"
            )
            return

        try:
            total_bytes, total_objects = _sync_buckets_to_external(settings)
            backup_run_repo.mark_success(
                db,
                backup_run,
                size_bytes=total_bytes,
                storage_location=f"{settings.BACKUP_S3_ENDPOINT}/{settings.BACKUP_S3_BUCKET}",
            )
            logger.info(
                f"backup_minio_objects: OK, {total_objects} objetos nuevos, "
                f"{total_bytes} bytes copiados a destino externo"
            )
        except Exception as e:
            logger.exception("backup_minio_objects: fallo")
            db.rollback()
            backup_run_repo.mark_failed(db, backup_run, error_message=str(e))
