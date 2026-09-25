"""Escaneo antivirus ASÍNCRONO de archivos grandes -- FileMeshy Worker (Ronda 9).

Por qué existe esta tarea (y no alcanza con `scan_for_malware` de Ronda 7):
subir un archivo de 10-15GB saturaba el servidor. La causa de fondo:
`scan_for_malware` (app/files/service.py) recibía `bytes` YA LEÍDOS
COMPLETOS en memoria del request síncrono -- y encima `clamd` de fábrica ni
siquiera acepta streams INSTREAM de más de unos cientos de MB
(`StreamMaxLength`/`MaxScanSize`/`MaxFileSize` en clamd.conf, confirmado
contra la imagen oficial, ver docker-compose.yml).

Arquitectura aprobada (mismo criterio que Nextcloud/ownCloud, con el
trade-off de seguridad explícito ya aceptado): antivirus asíncrono con GATE
DE VISIBILIDAD. El módulo `app/uploads/` (de otro agente/módulo, NO tocado
acá) sube archivos grandes DIRECTO a MinIO vía multipart presignado,
pasando por el proxy nuevo de nginx (`filemeshy_front/nginx.conf`, location
`/storage-proxy/`), y al completar la subida crea la fila `File` con
`scan_status='pending'` y encola esta tarea (`scan_uploaded_file.delay(...)`).
Esta tarea:

1. Adquiere un cupo del semáforo de concurrencia (Redis, ver
   `_try_acquire_scan_slot`/`_release_scan_slot`) -- protege a `clamd` de
   que varios archivos de 15-20GB terminando de subir casi a la vez
   disparen escaneos simultáneos que lo tumben (la propia documentación de
   ClamAV advierte esto si se suben los límites de tamaño sin acotar
   concurrencia). Si no consigue cupo, se REENCOLA (nunca bloquea el
   worker esperando) con `apply_async(countdown=...)`.

2. Escanea el objeto YA EN MINIO en streaming real (nunca en memoria del
   worker, ver `app.files.service.scan_minio_object_for_malware`).

3. Limpio -> `scan_status='clean'` (recién ahí el archivo es visible/
   servible -- ver el gate del lado API, propiedad de `app/files/`, no de
   este módulo) + notifica al dueño.

4. Infectado -> cuarentena REAL (mueve el objeto a un bucket separado,
   nunca lo deja en el bucket normal ni lo descarga a memoria del worker
   para moverlo) + `scan_status='infected'` + notifica al dueño con
   severidad alta. La fila `File` NUNCA se borra -- mismo criterio de todo
   el proyecto de dejar rastro auditable en vez de borrado silencioso.

5. `clamd` inalcanzable/timeout/MinIO no responde -> fail-closed, igual
   criterio que Ronda 7: el archivo NUNCA pasa a 'clean' sin una
   confirmación real. Reintenta con backoff (hasta `AV_SCAN_MAX_ERROR_
   RETRIES`, mismo techo que `task_max_retries=3` global de
   app/worker/celery_app.py) y si se agotan, `scan_status='scan_failed'`
   (estado NUEVO, distinto de 'pending' a propósito -- ver docstring de
   `_handle_scan_infra_error` para por qué) + notifica con severidad alta
   que requiere atención manual. Nunca queda colgado en silencio.

Constantes de este módulo, NUNCA agregadas a `app/core/config.py` a
propósito (ese archivo es propiedad de otro agente/módulo en esta ronda,
ver instrucciones de la tarea) -- todas overrideables por variable de
entorno si hace falta ajustarlas sin tocar código.
"""

import logging
import os
import time
from typing import Optional
from uuid import UUID

from app.worker.celery_app import celery_app
from app.worker.db import get_worker_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes locales (ver docstring del módulo -- nunca en app/core/config.py)
# ---------------------------------------------------------------------------

# Cupo máximo de escaneos INSTREAM simultáneos contra `clamd` -- ver
# `_try_acquire_scan_slot`. Default 2: coincide con el número usado en las
# mediciones en vivo de mem_limit del servicio `clamav` (docker-compose.yml,
# comentario del servicio) -- si se cambia este valor, revisar también esa
# medición (más cupo simultáneo = más memoria pico real posible).
AV_SCAN_CONCURRENCY_LIMIT = int(os.getenv("AV_SCAN_CONCURRENCY_LIMIT", "2"))

# Cuánto esperar antes de reintentar cuando NO hay cupo de concurrencia
# (nunca cuenta como "intento fallido" real -- ver `_requeue_for_concurrency`).
AV_SCAN_REQUEUE_COUNTDOWN_SECONDS = int(os.getenv("AV_SCAN_REQUEUE_COUNTDOWN_SECONDS", "30"))

# Deadline TOTAL del escaneo INSTREAM en sí (ver `_run_instream_scan` en
# app/files/service.py) -- MUY por encima del default de
# `CLAMAV_SCAN_TIMEOUT_SECONDS` (30s, pensado para requests síncronos
# chicos), porque acá el archivo puede ser de hasta `MAX_LARGE_UPLOAD_SIZE_MB`
# (20GB, asumido -- confirmar con el módulo de uploads si difiere). Medido en
# vivo (Ronda 9, ver docker-compose.yml): un stream de 6GB tardó ~9-13s a
# través de la red interna de Docker -- 30 minutos deja margen de sobra
# incluso para un `clamd` bajo carga o un archivo de 20GB completo a menor
# throughput.
AV_SCAN_LARGE_FILE_TIMEOUT_SECONDS = int(os.getenv("AV_SCAN_LARGE_FILE_TIMEOUT_SECONDS", "1800"))

# Reintentos ante error de INFRAESTRUCTURA (clamd caído/timeout, MinIO no
# responde) -- NO ante "infectado" (eso no es un error, es un resultado
# válido, nunca se reintenta). Mismo techo que `task_max_retries=3` global
# de app/worker/celery_app.py, expuesto acá como constante propia para el
# chequeo EXPLÍCITO de `_handle_scan_infra_error` (no se depende del
# `MaxRetriesExceededError` implícito de Celery -- ver esa función).
AV_SCAN_MAX_ERROR_RETRIES = int(os.getenv("AV_SCAN_MAX_ERROR_RETRIES", "3"))
AV_SCAN_ERROR_RETRY_BASE_SECONDS = int(os.getenv("AV_SCAN_ERROR_RETRY_BASE_SECONDS", "60"))

# Bucket de cuarentena -- privado, nunca con política de lectura pública
# (mismo criterio que `filemeshy-media-private`, ver `_ensure_private_bucket`
# en app/files/service.py). Bootstrapping perezoso (se crea la primera vez
# que hace falta, igual que el resto de los buckets del proyecto -- no hay
# un init-container de `mc mb` en este stack, ver docker-compose.yml) --
# nada que agregar ahí para "crear" este bucket.
MINIO_QUARANTINE_BUCKET = os.getenv("MINIO_QUARANTINE_BUCKET", "filemeshy-quarantine")

# Tope de tamaño para encolar indexación de contenido (Ronda 6,
# `app.worker.tasks.indexing.index_file_content`) sobre un archivo que
# llegó por el camino grande -- ver docstring completo de
# `_enqueue_content_indexing` más abajo (esa tarea lee el objeto COMPLETO a
# memoria, no fue diseñada para streaming). 512MB es generoso para
# cualquier documento de texto/PDF/Office real -- por encima de eso, el
# archivo queda 'clean' (visible/descargable/previsualizable) pero no se
# indexa por contenido, limitación conocida y documentada.
AV_SCAN_INDEXING_MAX_SIZE_BYTES = int(os.getenv("AV_SCAN_INDEXING_MAX_SIZE_BYTES", str(512 * 1024 * 1024)))

# Límites de tiempo del lado Celery para la tarea completa -- deben quedar
# POR ENCIMA del deadline interno del escaneo (AV_SCAN_LARGE_FILE_TIMEOUT_
# SECONDS) para dejarle margen a la lógica de después (marcar estado,
# notificar) una vez que el escaneo en sí corta por su propio deadline.
TASK_TIME_LIMIT_SECONDS = AV_SCAN_LARGE_FILE_TIMEOUT_SECONDS + 300
TASK_SOFT_TIME_LIMIT_SECONDS = AV_SCAN_LARGE_FILE_TIMEOUT_SECONDS + 120

# Límite real de un solo `CopyObject` de S3/MinIO -- objetos más grandes
# necesitan multipart-copy (ver `_copy_object_to_quarantine`). 5GiB es el
# límite documentado de la operación; se deja margen chico debajo.
_MAX_SINGLE_COPY_BYTES = 5 * 1024 ** 3 - 1024
# Tamaño de cada parte en el multipart-copy -- generoso y bien por debajo
# del límite de 5GiB por parte de `UploadPartCopy`, y por encima del mínimo
# real de 5MiB por parte que exige S3/MinIO (salvo la última parte).
_MULTIPART_COPY_PART_SIZE = 500 * 1024 ** 2


# ---------------------------------------------------------------------------
# Semáforo de concurrencia (Redis) -- ver punto 1 del docstring del módulo
# ---------------------------------------------------------------------------
# Mismo cliente de cache que usa `RateLimiter` (app/auth/service.py) --
# reusado acá en vez de abrir una conexión Redis propia. Patrón simple:
# INCR con tope (si supera el límite, DECR inmediato para "devolver" el
# cupo que no se pudo usar) + DECR al liberar. Con `expire()` de seguridad
# en la clave (TTL generoso) para que un worker que muere sin liberar su
# cupo (crash, OOM-kill, `kill -9`) no deje el semáforo trabado para
# siempre -- se autolimpia solo, aunque en el peor caso subestime
# temporalmente cuánto cupo hay libre (mejor eso que un semáforo roto que
# nunca vuelve a dar cupo).
#
# Fail-open A PROPÓSITO si Redis no está disponible: este semáforo es
# protección de RECURSOS (no tumbar `clamd`), no la política de seguridad
# del escaneo en sí -- si Redis falla, se prefiere seguir escaneando (con
# el riesgo de más concurrencia de la ideal) antes que bloquear TODOS los
# uploads grandes por una dependencia que no es la fuente de verdad de
# "¿este archivo tiene malware?". El resultado del escaneo (limpio/
# infectado) sigue siendo SIEMPRE fail-closed, sin excepción -- eso no
# depende de Redis en ningún punto de este archivo.
_SEMAPHORE_KEY = "av_scan:active_scans"
_SEMAPHORE_SAFETY_TTL_SECONDS = AV_SCAN_LARGE_FILE_TIMEOUT_SECONDS * 3


def _get_redis_client():
    from app.core.cache import cache

    if cache.enabled and cache.client:
        return cache.client
    return None


def _try_acquire_scan_slot() -> bool:
    """True si se consiguió cupo (el caller YA puede escanear -- debe
    llamar `_release_scan_slot` cuando termine, en un `finally`). False si
    no hay cupo disponible ahora mismo (el caller debe reencolar, nunca
    esperar bloqueado)."""
    redis_client = _get_redis_client()
    if redis_client is None:
        logger.warning(
            "[AVScan] Redis no disponible -- semáforo de concurrencia deshabilitado, "
            "se escanea igual (fail-open SOLO para este límite de recursos, nunca "
            "para el resultado del escaneo)"
        )
        return True

    try:
        current = redis_client.incr(_SEMAPHORE_KEY)
        if current == 1:
            redis_client.expire(_SEMAPHORE_KEY, _SEMAPHORE_SAFETY_TTL_SECONDS)
        if current > AV_SCAN_CONCURRENCY_LIMIT:
            redis_client.decr(_SEMAPHORE_KEY)
            return False
        return True
    except Exception as e:
        logger.warning(f"[AVScan] Error usando Redis para el semáforo de concurrencia: {e} -- fail-open")
        return True


def _release_scan_slot() -> None:
    redis_client = _get_redis_client()
    if redis_client is None:
        return
    try:
        new_value = redis_client.decr(_SEMAPHORE_KEY)
        if new_value < 0:
            # Nunca debería pasar en el camino feliz -- red de seguridad
            # ante algún desbalance INCR/DECR (ej. un release duplicado).
            redis_client.set(_SEMAPHORE_KEY, 0)
    except Exception as e:
        logger.warning(f"[AVScan] Error liberando el semáforo de concurrencia: {e}")


# ---------------------------------------------------------------------------
# Cuarentena -- mover (no copiar y dejar) el objeto infectado, server-side
# ---------------------------------------------------------------------------

def _copy_object_to_quarantine(client, *, source_bucket: str, key: str, size_bytes: int) -> None:
    """Server-side copy de `source_bucket/key` a `MINIO_QUARANTINE_BUCKET`
    (misma key) -- el contenido NUNCA pasa por este proceso (worker), MinIO
    copia directo entre sus propios buckets.

    Objetos > 5GiB necesitan multipart-copy: `CopyObject` de una sola
    llamada tiene un límite real de 5GiB en la API de S3 (y MinIO lo
    respeta) -- con `MAX_LARGE_UPLOAD_SIZE_MB` en 20GB, un archivo
    infectado grande cae en este camino con frecuencia, así que NO es un
    caso raro a ignorar (a diferencia de lo que sugeriría "copy_object
    simple alcanza" sin verificar el límite real de la operación)."""
    if size_bytes <= _MAX_SINGLE_COPY_BYTES:
        client.copy_object(
            Bucket=MINIO_QUARANTINE_BUCKET,
            Key=key,
            CopySource={"Bucket": source_bucket, "Key": key},
        )
        return

    upload = client.create_multipart_upload(Bucket=MINIO_QUARANTINE_BUCKET, Key=key)
    upload_id = upload["UploadId"]
    parts = []
    try:
        part_number = 1
        offset = 0
        while offset < size_bytes:
            end = min(offset + _MULTIPART_COPY_PART_SIZE, size_bytes) - 1
            result = client.upload_part_copy(
                Bucket=MINIO_QUARANTINE_BUCKET,
                Key=key,
                UploadId=upload_id,
                PartNumber=part_number,
                CopySource={"Bucket": source_bucket, "Key": key},
                CopySourceRange=f"bytes={offset}-{end}",
            )
            parts.append({"PartNumber": part_number, "ETag": result["CopyPartResult"]["ETag"]})
            offset = end + 1
            part_number += 1
        client.complete_multipart_upload(
            Bucket=MINIO_QUARANTINE_BUCKET,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
    except Exception:
        try:
            client.abort_multipart_upload(Bucket=MINIO_QUARANTINE_BUCKET, Key=key, UploadId=upload_id)
        except Exception:
            logger.exception(f"[AVScan] No se pudo abortar el multipart-copy a cuarentena de {source_bucket}/{key}")
        raise


def _quarantine_file(db, file_obj, threat_name: str) -> None:
    """Mueve el objeto infectado a `MINIO_QUARANTINE_BUCKET` (copy server-
    side + delete del original -- nunca queda en los dos lados) y marca
    `scan_status='infected'`. La fila `File` se conserva (nunca se borra --
    rastro auditable, mismo criterio que el resto del proyecto).

    Libera la cuota reservada del dueño (`release_upload_bytes`) -- hallazgo
    de la revisión adversarial (2026-09-22, severidad MEDIA): sin esto, los
    bytes de un archivo infectado quedaban contados PARA SIEMPRE en
    `bytes_used`, sin ningún camino de recuperación (el usuario ni siquiera
    puede ver/borrar un archivo en cuarentena para liberar el espacio él
    mismo) -- una fuga de cuota permanente por archivo infectado. Mismo
    criterio que ya usa `app/uploads/service.py` en sus caminos de
    fallo/abort (`release_upload_bytes(db, owner_id, bytes)`)."""
    from app.core.config import settings
    from app.files.service import _ensure_private_bucket, _get_client
    from app.storage_quota.service import release_upload_bytes

    client = _get_client()
    if not client:
        raise RuntimeError("El servicio de almacenamiento (MinIO) no está disponible para poner en cuarentena")

    _ensure_private_bucket(MINIO_QUARANTINE_BUCKET)

    source_bucket = settings.MINIO_PRIVATE_BUCKET
    key = file_obj.storage_key

    _copy_object_to_quarantine(client, source_bucket=source_bucket, key=key, size_bytes=file_obj.size_bytes)
    client.delete_object(Bucket=source_bucket, Key=key)

    file_obj.scan_status = "infected"
    db.commit()

    release_upload_bytes(db, file_obj.owner_id, file_obj.size_bytes)

    logger.warning(f"[AVScan] {file_obj.id} infectado ({threat_name}) -- movido a cuarentena ({MINIO_QUARANTINE_BUCKET}/{key}), cuota liberada")
    _notify_file_infected(db, file_obj, threat_name)


# ---------------------------------------------------------------------------
# Notificaciones -- reusa el sistema existente (Ronda 1), mismo patrón que
# la notificación de cuota (app/storage_quota/service.py)
# ---------------------------------------------------------------------------
# `notif_type="sistema"` (no se agrega un valor nuevo al enum
# `NotificationType` de app/notifications/schemas.py): el frontend
# (`NotificacionesPage.tsx`) ya tiene precedente de tipos usados del lado
# backend sin entrada propia en su `TYPE_CONFIG` (ej. "almacenamiento" de
# Ronda 1) -- degradan al ícono/label genérico sin romper nada. Evita tocar
# un archivo que no es estrictamente mío en esta ronda y evita depender de
# que el agente de frontend (que NO debe tocarse en esta ronda) agregue un
# mapeo nuevo para que esto se vea bien.

def _enqueue_content_indexing(file_obj) -> None:
    """Encola la extracción de texto/OCR (Ronda 6,
    `app.worker.tasks.indexing.index_file_content`) para `file_obj`, recién
    marcado `scan_status='clean'` -- MISMO criterio que
    `app/files/router.py::_enqueue_content_indexing` (best-effort, import
    diferido para evitar ciclo de import, nunca revienta el escaneo si
    Celery/Redis no están disponibles en este momento).

    Hallazgo de la revisión adversarial (2026-09-22, funcional): sin esto,
    un archivo subido por el camino grande NUNCA quedaba buscable por
    contenido -- `_enqueue_content_indexing` del router solo se dispara
    desde los 4 puntos del camino SÍNCRONO viejo, `app/uploads/` nunca la
    llama, y aunque la llamara, `index_file_content` habría intentado leer
    un `File` todavía 'pending' (mismo gate de visibilidad que forzó crear
    `get_for_scan_worker`, ver más arriba) -- este es el único punto
    correcto: justo cuando el archivo pasa a 'clean' de verdad.

    Tope de tamaño propio (`AV_SCAN_INDEXING_MAX_SIZE_BYTES`) -- decisión de
    diseño explícita, no en la lista original: `index_file_content` NO fue
    diseñada para streaming, lee el objeto COMPLETO a memoria
    (`_read_private_object`) y las librerías de extracción
    (pypdf/openpyxl/python-docx/pytesseract) también necesitan el contenido
    completo en memoria para parsear. Encolarla sin tope reintroduciría, en
    el worker de indexación, el mismo problema de memoria que esta ronda
    entera existe para resolver del lado del escaneo -- para un archivo de
    varios GB sería directamente inviable. No se modifica `indexing.py`
    para agregarle un tope propio (fuera del alcance de archivos de este
    agente) -- el tope se aplica ACÁ, en el punto donde se decide encolar o
    no. Por encima del tope, el archivo queda perfectamente usable (visible,
    descargable, previsualizable) pero no aparece en resultados de búsqueda
    por CONTENIDO -- limitación conocida y documentada, no un olvido
    silencioso (la inmensa mayoría de archivos realmente grandes -- video,
    backups, ISOs, datasets -- no son indexables por contenido de todos
    modos, así que el impacto práctico del tope es chico)."""
    if file_obj.size_bytes > AV_SCAN_INDEXING_MAX_SIZE_BYTES:
        logger.info(
            f"[AVScan] {file_obj.id} ({file_obj.size_bytes} bytes) supera el tope de indexación "
            f"async ({AV_SCAN_INDEXING_MAX_SIZE_BYTES} bytes) -- queda 'clean' pero no se indexa "
            "por contenido (limitación conocida, ver docstring de _enqueue_content_indexing)."
        )
        return

    try:
        from app.core.database import tenant_schema_ctx
        from app.worker.tasks.indexing import index_file_content

        index_file_content.delay(tenant_schema_ctx.get(), str(file_obj.id))
    except Exception as exc:
        logger.warning(f"[AVScan] No se pudo encolar indexación de contenido para {file_obj.id}: {exc}")


def _notify_file_clean(db, file_obj) -> None:
    from app.worker.tasks.notification_helpers import create_notification

    create_notification(
        db=db,
        user_id=file_obj.owner_id,
        title="Tu archivo ya está disponible",
        message=f'"{file_obj.name}" terminó de escanearse sin encontrar amenazas y ya está disponible en tu Drive.',
        notif_type="sistema",
        severity="success",
        extra_data={"reference_id": str(file_obj.id), "file_id": str(file_obj.id)},
    )


def _notify_file_infected(db, file_obj, threat_name: str) -> None:
    from app.worker.tasks.notification_helpers import create_notification

    create_notification(
        db=db,
        user_id=file_obj.owner_id,
        title="Archivo removido por seguridad",
        message=(
            f'"{file_obj.name}" fue detectado como malicioso ({threat_name}) durante el escaneo '
            "y se movió a cuarentena. El archivo ya NO está disponible en tu Drive."
        ),
        notif_type="sistema",
        severity="error",
        extra_data={"reference_id": str(file_obj.id), "file_id": str(file_obj.id), "threat_name": threat_name},
    )


def _notify_scan_needs_attention(db, file_obj, error_message: str) -> None:
    from app.worker.tasks.notification_helpers import create_notification

    create_notification(
        db=db,
        user_id=file_obj.owner_id,
        title="No se pudo confirmar que tu archivo esté limpio",
        message=(
            f'"{file_obj.name}" lleva varios intentos sin poder escanearse (el servicio de antivirus '
            "no respondió). Por seguridad el archivo sigue oculto hasta que el equipo lo revise manualmente."
        ),
        notif_type="sistema",
        severity="error",
        extra_data={"reference_id": str(file_obj.id), "file_id": str(file_obj.id), "error": error_message[:300]},
    )


# ---------------------------------------------------------------------------
# Manejo de error de infraestructura (clamd caído/timeout, MinIO no responde)
# ---------------------------------------------------------------------------

def _handle_scan_infra_error(task, db, file_obj, error: Exception) -> None:
    """Reintenta con backoff hasta `AV_SCAN_MAX_ERROR_RETRIES`. Chequeo
    EXPLÍCITO de `task.request.retries` en vez de dejar que Celery dispare
    `MaxRetriesExceededError` -- así se decide acá mismo, sin ambigüedad,
    cuándo pasar de "reintentar" a "marcar como que necesita atención
    manual", sin depender de distinguir excepciones internas de Celery.

    Reintentos agotados -> `scan_status='scan_failed'` (estado NUEVO,
    decisión de diseño de esta ronda: se prefirió un estado explícito en
    vez de dejarlo en 'pending' con un timestamp "viejo" -- un admin/
    dashboard futuro puede filtrar por 'scan_failed' directo, sin tener que
    calcular "¿hace cuánto que está pending?" contra `created_at` en cada
    lugar que necesite distinguir "recién subido" de "requiere atención".
    `File.scan_status` es un `String` simple sin CHECK constraint en DB,
    mismo patrón que `FileContentIndex.extraction_status` -- agregar un
    valor nuevo no requiere migración. Fail-closed real: en NINGÚN punto de
    este camino el archivo pasa a 'clean' sin una confirmación positiva de
    `clamd`)."""
    attempt = task.request.retries
    if attempt < AV_SCAN_MAX_ERROR_RETRIES:
        backoff = AV_SCAN_ERROR_RETRY_BASE_SECONDS * (2 ** attempt)
        logger.warning(
            f"[AVScan] Error de infraestructura escaneando {file_obj.id} "
            f"(intento {attempt + 1}/{AV_SCAN_MAX_ERROR_RETRIES}, reintenta en {backoff}s): {error}"
        )
        raise task.retry(exc=error, countdown=backoff)

    logger.error(
        f"[AVScan] Reintentos agotados escaneando {file_obj.id} -- requiere atención manual: {error}"
    )
    file_obj.scan_status = "scan_failed"
    db.commit()
    _notify_scan_needs_attention(db, file_obj, str(error))


# ---------------------------------------------------------------------------
# Tarea principal
# ---------------------------------------------------------------------------

def _requeue_for_concurrency(file_id: str, tenant_schema: Optional[str] = None) -> None:
    """Reencola una invocación NUEVA (no un `self.retry()`) cuando no hay
    cupo de concurrencia -- a propósito NO usa el mecanismo de retry de
    Celery para esto: `self.retry()` incrementa `self.request.retries`, el
    MISMO contador que `_handle_scan_infra_error` usa para decidir cuándo
    dar por perdido un escaneo real (clamd caído). Si "esperar cupo" y
    "clamd está caído" compartieran contador, un archivo grande podría
    quedar marcado `scan_failed` solo por haber esperado cupo unas cuantas
    veces en un momento de mucha carga -- un falso positivo de "necesita
    atención manual" que en realidad nunca tuvo un error real. Por eso acá
    se reencola con `apply_async` normal, una invocación fresca con
    `self.request.retries == 0`."""
    scan_uploaded_file.apply_async(args=[file_id, tenant_schema], countdown=AV_SCAN_REQUEUE_COUNTDOWN_SECONDS)


@celery_app.task(
    bind=True,
    max_retries=AV_SCAN_MAX_ERROR_RETRIES,
    name="app.worker.tasks.av_scan.scan_uploaded_file",
    queue="av_scan",
    time_limit=TASK_TIME_LIMIT_SECONDS,
    soft_time_limit=TASK_SOFT_TIME_LIMIT_SECONDS,
)
def scan_uploaded_file(self, file_id: str, tenant_schema: Optional[str] = None):
    """Escanea `file_id` (subido grande, vía `app/uploads/`) DESDE MinIO en
    streaming real -- ver docstring del módulo para el flujo completo.

    Contrato: `scan_uploaded_file(file_id, tenant_schema=None)`. El segundo
    argumento es opcional para seguir aceptando mensajes ya encolados con un
    solo argumento (`.delay(str(file_id))`). En `DEPLOYMENT_MODE=cloud`,
    `app/uploads/service.py::_enqueue_av_scan` encola con el schema del
    tenant (`tenant_schema_ctx.get()`) y esta tarea lo usa en
    `get_worker_db(schema_name=tenant_schema)`; se propaga también al
    reencolado por concurrencia y a los reintentos (`self.retry` reutiliza
    `request.args`, que ya incluyen el schema). Sin schema (modo local)
    se comporta igual que siempre.

    Idempotente ante reencolados/duplicados: si `file_obj.scan_status` ya
    no es `'pending'` cuando corre (otro worker ya lo procesó), no hace
    nada -- evita notificar dos veces o intentar poner en cuarentena un
    objeto que ya se movió."""
    if not _try_acquire_scan_slot():
        logger.info(
            f"[AVScan] Sin cupo de concurrencia (límite={AV_SCAN_CONCURRENCY_LIMIT}) -- "
            f"reencolando {file_id} en {AV_SCAN_REQUEUE_COUNTDOWN_SECONDS}s"
        )
        _requeue_for_concurrency(file_id, tenant_schema)
        return

    try:
        from app.core.config import settings
        from app.files.repository import file_repo
        from app.files.service import scan_minio_object_for_malware

        with get_worker_db(schema_name=tenant_schema) as db:
            # `get_for_scan_worker` (no `get()`) a propósito -- `file_repo.get()`
            # filtra `scan_status == 'clean'` (gate de visibilidad, ver
            # docstring de `CRUDFile` en app/files/repository.py), así que
            # jamás encontraría un archivo todavía 'pending', que es
            # exactamente el que esta tarea necesita leer para poder
            # actualizarlo a 'clean'/'infected'.
            file_obj = file_repo.get_for_scan_worker(db, UUID(str(file_id)))
            if file_obj is None:
                logger.warning(f"[AVScan] Archivo {file_id} no existe (¿borrado antes de escanear?)")
                return

            if file_obj.scan_status != "pending":
                logger.info(
                    f"[AVScan] {file_id} ya no está 'pending' (scan_status={file_obj.scan_status!r}) "
                    "-- se omite (reencolado duplicado o ya procesado)"
                )
                return

            start = time.monotonic()
            try:
                is_clean, threat_name = scan_minio_object_for_malware(
                    bucket=settings.MINIO_PRIVATE_BUCKET,
                    key=file_obj.storage_key,
                    timeout_seconds=AV_SCAN_LARGE_FILE_TIMEOUT_SECONDS,
                )
            except (ConnectionError, RuntimeError) as e:
                _handle_scan_infra_error(self, db, file_obj, e)
                return

            elapsed = time.monotonic() - start

            if is_clean:
                file_obj.scan_status = "clean"
                db.commit()
                logger.info(f"[AVScan] {file_id} limpio ({file_obj.size_bytes} bytes, {elapsed:.1f}s)")
                _notify_file_clean(db, file_obj)
                _enqueue_content_indexing(file_obj)
            else:
                _quarantine_file(db, file_obj, threat_name)
    finally:
        _release_scan_slot()
