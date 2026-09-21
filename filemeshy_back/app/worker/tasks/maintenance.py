"""
Tareas de mantenimiento — FileMeshy Worker.

Limpieza de datos obsoletos, consistencia e integridad.
"""

import logging
from datetime import datetime, timedelta, timezone

from app.worker.celery_app import celery_app
from app.worker.db import get_worker_db, iter_tenant_schemas

logger = logging.getLogger(__name__)


# Módulo dueño: auth.
@celery_app.task(name="app.worker.tasks.maintenance.cleanup_expired_sessions")
def cleanup_expired_sessions():
    """
    Elimina sesiones expiradas o inactivas, por tenant activo.
    Ejecuta cada 6 horas.
    """
    resultados = {}
    for schema in iter_tenant_schemas():
        clave = schema or "public"
        try:
            with get_worker_db(schema_name=schema) as db:
                from app.auth.models import Session
                from sqlalchemy import and_, or_

                now = datetime.now(timezone.utc)
                cutoff_inactive = now - timedelta(days=7)

                count = (
                    db.query(Session)
                    .filter(
                        or_(
                            Session.expires_at < now,
                            and_(Session.is_active == False, Session.last_activity < cutoff_inactive),
                        )
                    )
                    .delete(synchronize_session=False)
                )
                db.commit()
                logger.info(f"cleanup_expired_sessions: {count} sesiones eliminadas (tenant={clave})")
                resultados[clave] = {"eliminadas": count}
        except Exception:
            logger.exception(f"cleanup_expired_sessions: fallo en tenant '{clave}'")

    return resultados


# Módulo dueño: auth.
@celery_app.task(name="app.worker.tasks.maintenance.revoke_inactive_sessions")
def revoke_inactive_sessions(days: int = 30):
    """
    Revoca sesiones que no han tenido actividad en N días, por tenant activo.
    Ejecuta semanalmente (domingos 3:30 AM).
    """
    resultados = {}
    for schema in iter_tenant_schemas():
        clave = schema or "public"
        try:
            with get_worker_db(schema_name=schema) as db:
                from app.auth.models import Session

                cutoff = datetime.now(timezone.utc) - timedelta(days=days)

                count = (
                    db.query(Session)
                    .filter(
                        Session.is_active == True,
                        Session.last_activity < cutoff,
                    )
                    .update({"is_active": False}, synchronize_session=False)
                )
                db.commit()
                logger.info(f"revoke_inactive_sessions: {count} sesiones revocadas (>{days} días inactivas, tenant={clave})")
                resultados[clave] = {"revocadas": count}
        except Exception:
            logger.exception(f"revoke_inactive_sessions: fallo en tenant '{clave}'")

    return resultados


# Módulo dueño: notifications.
@celery_app.task(name="app.worker.tasks.maintenance.cleanup_old_notifications")
def cleanup_old_notifications(days: int = 30):
    """
    Elimina notificaciones leídas con más de N días, por tenant activo.
    Ejecuta semanalmente (domingos 3:00 AM).
    """
    resultados = {}
    for schema in iter_tenant_schemas():
        clave = schema or "public"
        try:
            with get_worker_db(schema_name=schema) as db:
                from app.notifications.models import Notification
                from sqlalchemy import and_

                cutoff = datetime.now(timezone.utc) - timedelta(days=days)

                count = (
                    db.query(Notification)
                    .filter(
                        and_(
                            Notification.is_read == True,
                            Notification.created_at < cutoff,
                        )
                    )
                    .delete(synchronize_session=False)
                )
                db.commit()
                logger.info(f"cleanup_old_notifications: {count} notificaciones leídas eliminadas (>{days} días, tenant={clave})")
                resultados[clave] = {"eliminadas": count}
        except Exception:
            logger.exception(f"cleanup_old_notifications: fallo en tenant '{clave}'")

    return resultados


# Módulo dueño: audit.
@celery_app.task(name="app.worker.tasks.maintenance.cleanup_old_audit_logs")
def cleanup_old_audit_logs(days: int = 90):
    """
    Elimina audit_logs con más de N días, por tenant activo.
    Ejecuta el primer domingo del mes a las 4:00 AM.
    El umbral respeta audit_configuration.log_retention_days si está configurado.
    """
    resultados = {}
    for schema in iter_tenant_schemas():
        clave = schema or "public"
        try:
            with get_worker_db(schema_name=schema) as db:
                from app.audit.models import AuditLog

                dias = days
                # Intentar leer retención desde configuración del sistema
                try:
                    from app.configuration.models import SystemConfiguration
                    config = (
                        db.query(SystemConfiguration)
                        .filter(SystemConfiguration.config_key == "log_retention_days")
                        .first()
                    )
                    if config and config.config_value:
                        dias = int(config.config_value)
                except Exception:
                    pass

                cutoff = datetime.now(timezone.utc) - timedelta(days=dias)

                count = (
                    db.query(AuditLog)
                    .filter(AuditLog.created_at < cutoff)
                    .delete(synchronize_session=False)
                )
                db.commit()
                logger.info(f"cleanup_old_audit_logs: {count} registros eliminados (>{dias} días, tenant={clave})")
                resultados[clave] = {"eliminados": count}
        except Exception:
            logger.exception(f"cleanup_old_audit_logs: fallo en tenant '{clave}'")

    return resultados


# Módulo dueño: files (MinIO).
@celery_app.task(name="app.worker.tasks.maintenance.cleanup_temp_files")
def cleanup_temp_files(max_age_hours: int = 24):
    """
    Elimina objetos temporales en MinIO bajo el prefijo 'temp/' con más de N horas.
    Los archivos temporales son exportaciones, previsualizaciones, etc. generadas por el sistema.
    Bucket único global (no hay uno por tenant) -- no depende de tenant_schema_ctx.
    Ejecuta diariamente a las 3:00 AM.
    """
    try:
        from app.core.config import settings
        import boto3
        from botocore.config import Config

        if not settings.MINIO_ENDPOINT:
            logger.info("cleanup_temp_files: MinIO no configurado, omitiendo")
            return {"eliminados": 0}

        client = boto3.client(
            "s3",
            endpoint_url=settings.MINIO_ENDPOINT,
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )

        bucket = settings.MINIO_BUCKET
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        eliminados = 0
        continuation_token = None

        while True:
            kwargs = {"Bucket": bucket, "Prefix": "temp/"}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            response = client.list_objects_v2(**kwargs)
            objects = response.get("Contents", [])

            for obj in objects:
                last_modified = obj["LastModified"]
                # boto3 devuelve datetime timezone-aware (UTC)
                if last_modified < cutoff:
                    client.delete_object(Bucket=bucket, Key=obj["Key"])
                    eliminados += 1
                    logger.debug(f"cleanup_temp_files: eliminado {obj['Key']}")

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

        logger.info(f"cleanup_temp_files: {eliminados} objetos temporales eliminados de MinIO")
        return {"eliminados": eliminados}

    except ImportError:
        logger.warning("cleanup_temp_files: boto3 no disponible")
        return {"eliminados": 0}
    except Exception as e:
        logger.error(f"cleanup_temp_files error: {e}")
        return {"eliminados": 0, "error": str(e)}


# Módulo dueño: files.
@celery_app.task(name="app.worker.tasks.maintenance.purge_deleted_files_and_folders")
def purge_deleted_files_and_folders(days: int = 30):
    """
    Purga definitiva de la papelera: archivos y carpetas con `deleted_at` de
    más de N días, por tenant activo. Antes de borrar la fila de un ARCHIVO,
    borra de MinIO el objeto de CADA una de sus versiones (Ronda 4 --
    `file_versions`, no solo el `storage_key` actual: cada versión subió un
    blob propio que se conserva como historial mientras el archivo existe, y
    el `ON DELETE CASCADE` de la FK borra las filas de `file_versions` pero
    NUNCA los objetos de MinIO -- eso hay que hacerlo a mano, ANTES de que el
    CASCADE se dispare) -- si algún borrado falla, se loggea y se sigue con
    el resto del batch en vez de abortar todo (un objeto huérfano en MinIO es
    preferible a una fila sin storage_key borrable). La cuota liberada es la
    suma de `size_bytes` de los blobs ÚNICOS de `file_versions`
    (`file_version_repo.get_total_size_for_file`, deduplicado por
    `storage_key` -- ver su docstring para el bug real que corrige: un
    restore crea una fila de historial que reapunta a un `storage_key` ya
    contado, sumar fila por fila sin deduplicar infla la liberación y
    arrastra cuota de OTROS archivos del mismo dueño), no solo
    `File.size_bytes` (la última) -- cada versión reservó cuota real y nunca
    se liberó al crear la siguiente (ver `_create_new_file_version` en
    app/files/router.py). Las carpetas no tienen storage propio -- solo se
    borra la fila.

    Los `shares` que apunten a un archivo/carpeta purgado se limpian solos
    por el `ON DELETE CASCADE` de la FK -- no hace falta lógica extra acá.
    Ejecuta diariamente a las 4:00 AM (staggered de cleanup-temp-files, 3 AM).
    """
    resultados = {}
    for schema in iter_tenant_schemas():
        clave = schema or "public"
        try:
            with get_worker_db(schema_name=schema) as db:
                # El import defensivo de "todos los modelos" que vivía acá
                # (para que configure_mappers() no reviente con las
                # relaciones ORM que resuelven "User"/"Role"/etc. como
                # string) quedó CENTRALIZADO en
                # `app.worker.celery_app._register_all_orm_models()` (corre
                # solo, a nivel de módulo y vía la señal
                # `worker_process_init`, antes de que cualquier tarea
                # corra) -- ver su docstring para el bug real de producción
                # (Ronda 6, 2026-09-21) que motivó centralizarlo: tenerlo
                # duplicado ad-hoc en cada tarea no alcanzaba, porque si
                # OTRA tarea sin el workaround corría primero en el mismo
                # proceso, el registry quedaba roto para siempre igual.
                from app.files.models import File, FileVersion, Folder
                from app.files.repository import file_version_repo
                from app.files.service import delete_private_file
                from app.storage_quota.repository import user_storage_quota_repo

                cutoff = datetime.now(timezone.utc) - timedelta(days=days)

                files_purgados = 0
                files_a_purgar = (
                    db.query(File)
                    .filter(File.deleted_at.isnot(None), File.deleted_at < cutoff)
                    .all()
                )
                for file_obj in files_a_purgar:
                    file_id, storage_key = file_obj.id, file_obj.storage_key
                    owner_id = file_obj.owner_id

                    # Todas las versiones del archivo (incluida la 1, la del
                    # upload original) -- cada una es un blob propio en
                    # MinIO. `storage_key` (la fila `File`, la versión más
                    # reciente) se agrega también por las dudas -- siempre
                    # debería coincidir con la última `FileVersion`, pero no
                    # cuesta nada cubrir el caso borde de que no coincida.
                    # El `set()` acá SÍ dedupe por `storage_key` para saber
                    # qué blobs ÚNICOS borrar de MinIO -- `total_size_bytes`
                    # usa el mismo criterio de deduplicación, ver
                    # `file_version_repo.get_total_size_for_file` (un restore
                    # crea una fila de historial que reapunta a un
                    # `storage_key` ya existente, sin bytes nuevos reales).
                    version_rows = (
                        db.query(FileVersion).filter(FileVersion.file_id == file_id).all()
                    )
                    storage_keys_to_delete = {storage_key} | {v.storage_key for v in version_rows}
                    total_size_bytes = (
                        file_version_repo.get_total_size_for_file(db, file_id)
                        if version_rows
                        else file_obj.size_bytes
                    )

                    for key in storage_keys_to_delete:
                        try:
                            delete_private_file(key)
                        except Exception:
                            logger.exception(
                                f"purge_deleted_files_and_folders: fallo borrando de MinIO "
                                f"'{key}' (file_id={file_id}), se continúa"
                            )
                    try:
                        db.delete(file_obj)
                        db.commit()
                        files_purgados += 1
                    except Exception:
                        db.rollback()
                        logger.exception(
                            f"purge_deleted_files_and_folders: fallo borrando fila de archivo "
                            f"{file_id}, se continúa"
                        )
                        continue

                    # Consumo real -- decrementar recién cuando la purga quedó
                    # confirmada (fila borrada). No se toca en soft-delete/restore
                    # (ver app/storage_quota/repository.py::adjust_bytes_used).
                    # `total_size_bytes` es la SUMA de todas las versiones, no
                    # solo la última (ver docstring de la tarea).
                    try:
                        user_storage_quota_repo.adjust_bytes_used(db, owner_id, -total_size_bytes)
                    except Exception:
                        # Mismo criterio que el except de arriba (borrado de fila): sin este
                        # rollback, un fallo transitorio de DB acá deja la sesión en
                        # transacción abortada y el resto del batch de esta corrida falla
                        # en cascada con errores engañosos (hallazgo de la revisión
                        # adversarial, Fase 3, 2026-09-08).
                        db.rollback()
                        logger.exception(
                            f"purge_deleted_files_and_folders: fallo actualizando cuota de "
                            f"almacenamiento de owner_id={owner_id} (file_id={file_id}), se continúa"
                        )

                carpetas_purgadas = (
                    db.query(Folder)
                    .filter(Folder.deleted_at.isnot(None), Folder.deleted_at < cutoff)
                    .delete(synchronize_session=False)
                )
                db.commit()

                logger.info(
                    f"purge_deleted_files_and_folders: {files_purgados} archivos y "
                    f"{carpetas_purgadas} carpetas purgados (>{days} días en papelera, tenant={clave})"
                )
                resultados[clave] = {"archivos": files_purgados, "carpetas": carpetas_purgadas}
        except Exception:
            logger.exception(f"purge_deleted_files_and_folders: fallo en tenant '{clave}'")

    return resultados
