"""
Tareas de subida multipart — FileMeshy Worker (Ronda 9).

Archivo nuevo separado de `app/worker/tasks/maintenance.py` a propósito
(preferencia del agente, ver instrucción de esta ronda: "O un archivo nuevo
app/worker/tasks/uploads.py, tu preferencia") -- mismo criterio que
`app/worker/tasks/backups.py` (Ronda 7) o `indexing.py` (Ronda 6): un módulo
nuevo entero es más fácil de revisar en un diff que agregarle una tarea más
a `maintenance.py`, que ya cubre sesiones/notificaciones/audit-logs/archivos
temporales/papelera -- dominios sin relación real con "subida multipart"
salvo por correr en la misma cola.
"""

import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.worker.celery_app import celery_app
from app.worker.db import get_worker_db, iter_tenant_schemas

logger = logging.getLogger(__name__)


# Módulo dueño: uploads.
@celery_app.task(name="app.worker.tasks.uploads.cleanup_abandoned_upload_sessions")
def cleanup_abandoned_upload_sessions():
    """
    Sesiones de subida multipart `'in_progress'` cuyo `expires_at`
    (`settings.UPLOAD_SESSION_EXPIRY_HOURS` desde la creación, ver
    `app/uploads/models.py::UploadSession`) ya pasó -- se consideran
    abandonadas (el cliente cerró la pestaña, se quedó sin batería, lo que
    sea) y nadie las va a completar ni abortar a mano. Por tenant activo,
    mismo patrón que el resto de tareas periódicas de mantenimiento (ver
    `app/worker/tasks/maintenance.py`).

    Por cada una: aborta el multipart REAL en MinIO
    (`abort_multipart_upload`, best-effort -- si ya no existe del lado de
    MinIO por el motivo que sea, se loggea y se sigue), libera la cuota
    reservada (`release_upload_bytes`, mismo helper que usa el abort manual
    del usuario en `app/uploads/service.py::abort_upload`) y marca la sesión
    `'aborted'`. También libera su cupo de admisión en Redis, si lo tenía
    (`release_admission_slot`) -- aunque en la práctica ya debería estar
    fuera de esa ventana temporal (el score del ZSET de admisión es el
    mismo `expires_at`, ver `app/uploads/service.py::_try_reserve_admission_slot`),
    liberar de más ahí es una operación idempotente sin efecto si ya no está.

    Procesa en tandas (`limit` de
    `app/uploads/repository.py::CRUDUploadSession.get_expired_in_progress`,
    default 200) -- si hay más pendientes que eso, quedan para la corrida
    siguiente (cada 6 horas, ver `beat_schedule` en
    `app/worker/celery_app.py`), nunca se intenta procesar un batch sin
    límite en una sola corrida.

    Ejecuta cada 6 horas (mismo intervalo que `cleanup_expired_sessions`,
    ver `beat_schedule`).
    """
    from app.uploads.repository import upload_session_repo
    from app.uploads.service import get_internal_client, release_admission_slot
    from app.storage_quota.service import release_upload_bytes

    resultados = {}
    for schema in iter_tenant_schemas():
        clave = schema or "public"
        try:
            with get_worker_db(schema_name=schema) as db:
                now = datetime.now(timezone.utc)
                expired = upload_session_repo.get_expired_in_progress(db, now=now)

                client = get_internal_client()
                abortadas = 0
                for session in expired:
                    if client is not None:
                        try:
                            client.abort_multipart_upload(
                                Bucket=settings.MINIO_PRIVATE_BUCKET,
                                Key=session.storage_key,
                                UploadId=session.minio_upload_id,
                            )
                        except Exception as exc:
                            logger.warning(
                                f"cleanup_abandoned_upload_sessions: abort_multipart_upload falló "
                                f"para session={session.id} (se continúa igual, cuota/estado se "
                                f"liberan del lado de la app): {exc}"
                            )

                    try:
                        release_upload_bytes(db, session.owner_id, session.quota_reserved_bytes)
                        upload_session_repo.mark_aborted(db, session)
                        release_admission_slot(session.id, session.owner_id)
                        abortadas += 1
                    except Exception:
                        db.rollback()
                        logger.exception(
                            f"cleanup_abandoned_upload_sessions: fallo liberando cuota/estado de "
                            f"session={session.id}, se continúa con el resto del batch"
                        )

                logger.info(
                    f"cleanup_abandoned_upload_sessions: {abortadas}/{len(expired)} sesiones "
                    f"abandonadas limpiadas (tenant={clave})"
                )
                resultados[clave] = {"abortadas": abortadas, "candidatas": len(expired)}
        except Exception:
            logger.exception(f"cleanup_abandoned_upload_sessions: fallo en tenant '{clave}'")

    return resultados
