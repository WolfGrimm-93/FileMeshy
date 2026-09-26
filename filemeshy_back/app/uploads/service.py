"""Servicio de subida multipart directa cliente→MinIO (Ronda 9).

Coordina lo que router.py expone en 4 pasos (`initiate` / `refresh-part-urls`
/ `complete` / `abort`): multipart real en MinIO (boto3, dos clientes
distintos -- ver `get_internal_client`/`_get_presign_client`, el porqué de
la separación está documentado en el segundo), cuota (reutiliza
`app.storage_quota.service`, nunca reimplementada acá) y admisión (tope de
subidas grandes simultáneas, Redis con fallback a un COUNT en DB).

Autocontenido a propósito: NO importa nada de `app.files.service` ni
`app.files.router` (son de otros dos agentes de esta misma ronda, tocarlos
está fuera de alcance) -- donde hace falta lógica equivalente (crear
`File`/`FileVersion`, generar `storage_key`, hablarle a MinIO) se reimplementa
acá, aunque implique algo de código repetido. Preferible a un conflicto de
merge.
"""

import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import cache
from app.core.config import settings
from app.files.models import File as FileModel, FileVersion
from app.files.repository import folder_repo
from app.shared.utils.uuid7 import uuid7
from app.storage_quota.service import release_upload_bytes, reserve_upload_bytes
from app.uploads.models import UploadSession
from app.uploads.repository import upload_session_repo
from app.uploads.schemas import (
    CompletedPartOut,
    PartUrlOut,
    RefreshPartUrlsResponse,
    UploadCompleteRequest,
    UploadInitiateRequest,
    UploadInitiateResponse,
)
from app.users.models import User

logger = logging.getLogger(__name__)

# Vigencia de una URL presignada de PARTE individual -- deliberadamente
# corta (a diferencia de `settings.UPLOAD_SESSION_EXPIRY_HOURS`, que es el
# plazo para RETOMAR la sesión completa): si venció, el cliente pide un lote
# nuevo con `POST /uploads/{id}/refresh-part-urls`, que además le informa
# qué partes ya no hace falta resubir (`ListParts` real). 4 horas es margen
# de sobra para subir una parte de 256MB incluso en una conexión lenta, sin
# dejar una URL firmada válida por más tiempo del necesario.
_PART_URL_EXPIRES_SECONDS = 4 * 3600

# Límite duro de S3/MinIO (no específico de este proyecto) -- ver
# https://docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html. Con los
# defaults de esta ronda (20GB / 256MB) da ~80 partes, muy por debajo; esta
# validación es defensa en profundidad para el día que alguien reconfigure
# `LARGE_UPLOAD_PART_SIZE_BYTES` mucho más chico sin bajar el tamaño máximo.
_S3_MAX_PART_COUNT = 10_000

# ---------------------------------------------------------------------------
# Clientes MinIO (boto3) -- DOS clientes separados a propósito.
# ---------------------------------------------------------------------------
_internal_client = None
_internal_client_ok = False
_presign_client = None
_presign_client_ok = False
_bucket_ensured: set[str] = set()


def get_internal_client():
    """Cliente boto3 para las llamadas REALES del backend a MinIO
    (`create_multipart_upload`, `list_parts`, `complete_multipart_upload`,
    `abort_multipart_upload`, `head_object`, `delete_object`) -- contra el
    endpoint INTERNO de la red Docker (`settings.MINIO_ENDPOINT`, ej.
    `http://minio:9000`). Mismo patrón que `app.files.service._get_client()`
    (reimplementado acá, no importado -- ver docstring del módulo)."""
    global _internal_client, _internal_client_ok
    if _internal_client_ok:
        return _internal_client
    if not settings.MINIO_ENDPOINT:
        logger.warning("[Uploads] MINIO_ENDPOINT no configurado -- subida multipart deshabilitada")
        return None
    try:
        import boto3
        from botocore.config import Config

        _internal_client = boto3.client(
            "s3",
            endpoint_url=settings.MINIO_ENDPOINT,
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        _internal_client_ok = True
        logger.info(f"[Uploads] Cliente interno MinIO inicializado en {settings.MINIO_ENDPOINT}")
    except Exception as exc:
        logger.error(f"[Uploads] Error inicializando cliente interno MinIO: {exc}")
        _internal_client = None
    return _internal_client


def _get_presign_client():
    """Cliente boto3 DEDICADO a firmar las URLs de `upload_part` que recibe
    el NAVEGADOR -- firma contra `settings.PUBLIC_STORAGE_PROXY_URL` (SOLO
    el host público, sin ningún sufijo de path, ver docstring del setting en
    `app/core/config.py`), NUNCA contra el endpoint interno (`MINIO_ENDPOINT`,
    ej. `http://minio:9000`, inalcanzable fuera de la red Docker). Mismo
    motivo que ya documenta `app.files.service._get_presign_client` para las
    descargas: la firma SigV4 incluye el host como canonical header -- si el
    navegador resuelve la URL contra un host distinto al firmado, MinIO
    recalcula la firma con el Host real de la request entrante y no
    coincide (403 AccessDenied).

    `addressing_style='path'` EXPLÍCITO (no el 'auto' que usa el cliente de
    arriba): la URL resultante queda
    `{PUBLIC_STORAGE_PROXY_URL}/{bucket}/{key}?X-Amz-...` -- el bucket como
    primer segmento del PATH (no subdominio virtual-hosted), exactamente el
    mismo patrón que ya sirve el location de descarga existente en
    `nginx.conf` (`~ ^/(filemeshy-media|filemeshy-media-private)/`, reusado
    también para subida en vez de un location `/storage-proxy/` dedicado --
    ver el hallazgo de la verificación en vivo de esta ronda). SigV4 firma
    tanto el Host COMO el path (CanonicalURI) -- un prefijo artificial
    delante del bucket (como el `/storage-proxy` del primer intento) rompe
    la firma sin importar cómo se configure nginx del otro lado, confirmado
    en vivo probando las 3 combinaciones contra MinIO real; por eso
    `PUBLIC_STORAGE_PROXY_URL` NO lleva sufijo y este cliente no le agrega
    ninguno tampoco."""
    global _presign_client, _presign_client_ok
    if _presign_client_ok:
        return _presign_client
    if not settings.PUBLIC_STORAGE_PROXY_URL:
        logger.warning("[Uploads] PUBLIC_STORAGE_PROXY_URL no configurado -- firma de partes deshabilitada")
        return None
    try:
        import boto3
        from botocore.config import Config

        _presign_client = boto3.client(
            "s3",
            endpoint_url=settings.PUBLIC_STORAGE_PROXY_URL,
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            region_name="us-east-1",
        )
        _presign_client_ok = True
        logger.info(f"[Uploads] Cliente de firma de partes inicializado en {settings.PUBLIC_STORAGE_PROXY_URL}")
    except Exception as exc:
        logger.error(f"[Uploads] Error inicializando cliente de firma de partes: {exc}")
        _presign_client = None
    return _presign_client


def _ensure_private_bucket(client, bucket: str) -> None:
    """Crea el bucket privado si no existe -- SIN política de lectura
    pública, mismo criterio que `app.files.service._ensure_private_bucket`
    (los archivos grandes son tan privados como cualquier otro archivo de
    usuario, van al MISMO bucket `settings.MINIO_PRIVATE_BUCKET`)."""
    if bucket in _bucket_ensured:
        return
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        try:
            client.create_bucket(Bucket=bucket)
            logger.info(f"[Uploads] Bucket privado '{bucket}' creado")
        except Exception as exc:
            logger.error(f"[Uploads] Error creando bucket privado '{bucket}': {exc}")
            return
    _bucket_ensured.add(bucket)


def _generate_part_urls(presign_client, bucket: str, storage_key: str, upload_id: str, part_numbers) -> list[PartUrlOut]:
    return [
        PartUrlOut(
            part_number=n,
            url=presign_client.generate_presigned_url(
                "upload_part",
                Params={"Bucket": bucket, "Key": storage_key, "PartNumber": n, "UploadId": upload_id},
                ExpiresIn=_PART_URL_EXPIRES_SECONDS,
            ),
        )
        for n in part_numbers
    ]


# ---------------------------------------------------------------------------
# Admisión: tope de subidas grandes SIMULTÁNEAS (protege el I/O de disco de
# MinIO, no la memoria del backend -- eso ya no aplica en este camino).
#
# Hallazgo de la revisión adversarial de seguridad (Ronda 9): la versión
# original de este bloque solo tenía un tope GLOBAL, sin ningún límite por
# usuario -- reproducido en vivo por el revisor, un solo usuario abriendo 8
# sesiones sin completar ni abortar ninguna llenaba el cupo global entero y
# bloqueaba la feature para TODOS los demás usuarios. Peor: el score del
# ZSET usaba el `expires_at` de 48hs de la sesión (el plazo para RETOMAR una
# subida, ver `settings.UPLOAD_SESSION_EXPIRY_HOURS`) como si fuera el TTL
# del cupo de concurrencia -- dos conceptos distintos que NO deberían
# compartir plazo. Un atacante podía bloquear el cupo global hasta 48-54hs
# (48hs de "vencimiento" + hasta 6hs más hasta que corriera la tarea
# periódica) con sesiones abandonadas a propósito, sin subir un solo byte.
#
# Dos correcciones, las dos necesarias:
#   1. Tope POR USUARIO (`MAX_CONCURRENT_LARGE_UPLOADS_PER_USER`) ADEMÁS del
#      global -- un ZSET propio por usuario (`_user_admission_key`), chequeo
#      y reserva de AMBOS (global + por-usuario) en el MISMO script Lua
#      atómico: si cualquiera de los dos está lleno, no se reserva NINGUNO.
#   2. El score de AMBOS ZSETs ya NO es `expires_at` (48hs) -- es un lease
#      corto e independiente (`LARGE_UPLOAD_ADMISSION_LEASE_HOURS`, unas
#      pocas horas, tiempo realista para subir hasta 20GB) que se renueva en
#      cada `POST /uploads/{id}/refresh-part-urls` (`_renew_admission_lease`)
#      mientras el usuario sigue activo. Una sesión abandonada de verdad deja
#      de contar contra CUALQUIERA de los dos topes en cuanto su lease corto
#      vence -- el chequeo de admisión ya poda (`ZREMRANGEBYSCORE`) los
#      miembros vencidos ANTES de contar, así que el cupo se autorecupera en
#      el momento del PRÓXIMO `/initiate` de cualquier usuario, sin depender
#      de que corra la tarea periódica de 6hs (esa tarea sigue existiendo
#      para limpiar la fila de `UploadSession` en DB y el multipart real en
#      MinIO -- lo que cambia acá es que el CUPO DE CONCURRENCIA ya no queda
#      atado a esperarla).
#
# Set ordenado de Redis (ZSET): miembro = id de sesión, score = timestamp
# unix de cuándo esa sesión deja de contar para el cupo de concurrencia.
# Chequeo+reserva atómicos vía un script Lua (EVAL) -- un ZCARD seguido de
# un ZADD en dos pasos separados tiene la MISMA ventana de carrera que ya se
# documentó (y resolvió) para la cuota de almacenamiento en
# app/storage_quota/repository.py::reserve_bytes_or_fail: dos requests
# concurrentes justo en el límite podrían ver el mismo conteo y las dos
# pasar. No se reutiliza `RateLimiter` (app/auth/service.py) tal cual porque
# ese mecanismo cuenta INTENTOS en una ventana de tiempo (rate limiting),
# esto necesita un conteo de "cuántos siguen activos AHORA" (un gauge, no un
# contador de eventos) -- un ZSET con poda por score es la estructura
# correcta para eso, `RateLimiter` sirve de referencia de patrón (mismo
# cliente `cache`/Redis, mismo criterio de fallback), no de implementación
# reusable tal cual.
_ADMISSION_KEY = "uploads:concurrent:active"


def _user_admission_key(owner_id: UUID) -> str:
    return f"uploads:concurrent:user:{owner_id}"


# KEYS[1] = ZSET global, KEYS[2] = ZSET del usuario -- poda ambos por score
# ANTES de contar, y solo reserva (ZADD en los dos) si NINGUNO de los dos
# topes está lleno. Si cualquiera lo está, no toca ninguno de los dos ZSETs
# -- nunca reserva "a medias" (global sí, por-usuario no, o viceversa).
_ADMISSION_LUA = """
local global_key = KEYS[1]
local user_key = KEYS[2]
local now = tonumber(ARGV[1])
local member = ARGV[2]
local score = tonumber(ARGV[3])
local global_limit = tonumber(ARGV[4])
local user_limit = tonumber(ARGV[5])
redis.call('ZREMRANGEBYSCORE', global_key, '-inf', now)
redis.call('ZREMRANGEBYSCORE', user_key, '-inf', now)
local global_count = redis.call('ZCARD', global_key)
local user_count = redis.call('ZCARD', user_key)
if global_count >= global_limit or user_count >= user_limit then
    return 0
end
redis.call('ZADD', global_key, score, member)
redis.call('ZADD', user_key, score, member)
return 1
"""


def _admission_lease_score() -> float:
    return time.time() + settings.LARGE_UPLOAD_ADMISSION_LEASE_HOURS * 3600


def _try_reserve_admission_slot(db: Session, owner_id: UUID, session_id: UUID) -> bool:
    """True si hay lugar (global Y por-usuario, y ya quedó reservado en
    ambos); False si se alcanzó `settings.MAX_CONCURRENT_LARGE_UPLOADS` o
    `settings.MAX_CONCURRENT_LARGE_UPLOADS_PER_USER`. Fallback a un COUNT
    directo en `upload_sessions` (global Y por-usuario) si Redis no está
    disponible -- best-effort, sin la atomicidad del script Lua (dos
    requests concurrentes justo en el límite podrían pasar ambas), aceptable
    porque este tope protege un recurso de infraestructura (I/O de disco) de
    un pico razonable, no es un límite de seguridad duro en sí mismo (el
    límite POR USUARIO sí es defensa real contra acaparamiento -- ver
    docstring del bloque)."""
    redis_client = cache.client if (cache.enabled and cache.client) else None
    if redis_client is not None:
        try:
            result = redis_client.eval(
                _ADMISSION_LUA,
                2,
                _ADMISSION_KEY,
                _user_admission_key(owner_id),
                time.time(),
                str(session_id),
                _admission_lease_score(),
                settings.MAX_CONCURRENT_LARGE_UPLOADS,
                settings.MAX_CONCURRENT_LARGE_UPLOADS_PER_USER,
            )
            return bool(int(result))
        except Exception as exc:
            logger.warning(f"[Uploads] Admisión vía Redis falló, usando fallback DB: {exc}")

    global_ok = upload_session_repo.count_in_progress(db) < settings.MAX_CONCURRENT_LARGE_UPLOADS
    user_ok = upload_session_repo.count_in_progress_for_user(db, owner_id) < settings.MAX_CONCURRENT_LARGE_UPLOADS_PER_USER
    return global_ok and user_ok


def release_admission_slot(session_id: UUID, owner_id: UUID) -> None:
    redis_client = cache.client if (cache.enabled and cache.client) else None
    if redis_client is None:
        return
    try:
        redis_client.zrem(_ADMISSION_KEY, str(session_id))
        redis_client.zrem(_user_admission_key(owner_id), str(session_id))
    except Exception as exc:
        logger.warning(f"[Uploads] No se pudo liberar el cupo de admisión de session={session_id}: {exc}")


def _renew_admission_lease(session_id: UUID, owner_id: UUID) -> None:
    """Extiende el lease corto de concurrencia (NO el plazo de 48hs para
    retomar la sesión, ver docstring del bloque) -- se llama desde
    `refresh_part_urls`, la señal más clara de que el usuario sigue
    activamente subiendo (pidió URLs nuevas porque las anteriores están por
    vencer o volvió después de una interrupción). Un simple `ZADD` sobre un
    miembro ya existente solo actualiza su score -- no hace falta el script
    Lua acá (no hay ningún chequeo de límite que hacer, la sesión YA tiene
    su lugar reservado en ambos ZSETs, esto solo pospone cuándo deja de
    contar). Si el miembro ya no está (se podó por vencimiento antes de este
    refresh, o Redis no tenía nada porque se usó el fallback DB en
    `initiate`), `ZADD` simplemente lo crea de nuevo -- inofensivo, y
    autocorrige la contabilización de Redis para lo que sigue."""
    redis_client = cache.client if (cache.enabled and cache.client) else None
    if redis_client is None:
        return
    try:
        score = _admission_lease_score()
        redis_client.zadd(_ADMISSION_KEY, {str(session_id): score})
        redis_client.zadd(_user_admission_key(owner_id), {str(session_id): score})
    except Exception as exc:
        logger.warning(f"[Uploads] No se pudo renovar el lease de admisión de session={session_id}: {exc}")


# ---------------------------------------------------------------------------
# Escaneo de AV -- encolado best-effort de la tarea del OTRO agente.
# ---------------------------------------------------------------------------

def _enqueue_av_scan(file_id: UUID) -> None:
    """Encola el escaneo asíncrono de AV. La tarea real
    (`app.worker.tasks.av_scan.scan_uploaded_file`) la construye el agente de
    infra/antivirus de esta misma ronda, en paralelo -- import diferido
    (mismo criterio que `_enqueue_content_indexing` en
    `app/files/router.py`) para que este módulo no dependa a nivel de import
    de que ese módulo ya exista, y best-effort con captura amplia: si
    todavía no existe (desarrollo en paralelo) o Celery/Redis no está
    disponible, la subida NO debe fallar por esto -- el archivo queda
    `scan_status='pending'` en la fila `File` y sencillamente no se escanea
    hasta que algo lo encole (manualmente, o cuando ese módulo exista de
    verdad)."""
    try:
        from app.core.database import tenant_schema_ctx
        from app.worker.tasks.av_scan import scan_uploaded_file

        # Schema del tenant (None en modo local) para que el worker abra la
        # sesión contra el schema correcto en modo cloud.
        scan_uploaded_file.delay(str(file_id), tenant_schema_ctx.get())
    except Exception as exc:
        logger.warning(f"[Uploads] No se pudo encolar el escaneo de AV para file_id={file_id}: {exc}")


def _fail_after_complete(db: Session, session: UploadSession, client, bucket: str, *, reason: str) -> None:
    """Camino de fallo DESPUÉS de que `complete_multipart_upload` ya corrió
    con éxito en MinIO -- a esa altura el objeto YA está completo y no se
    puede "abortar" (`abort_multipart_upload` solo aplica a multiparts en
    curso). Se borra el objeto resultante (best-effort), se libera TODA la
    cuota reservada y la sesión queda `'failed'` SIN `file_id` -- nunca se
    crea el `File`. Usado tanto si el tamaño real superó lo reservado como
    si no se pudo siquiera verificar (`head_object` falló) -- política
    fail-safe, mismo espíritu que el resto de la app (ej. `scan_for_malware`
    fail-closed): ante la duda, no se expone el archivo."""
    try:
        client.delete_object(Bucket=bucket, Key=session.storage_key)
    except Exception:
        logger.warning(
            f"[Uploads] No se pudo borrar el objeto huérfano tras fallo post-complete "
            f"(session={session.id}, key={session.storage_key}) -- queda huérfano en MinIO"
        )
    release_upload_bytes(db, session.owner_id, session.quota_reserved_bytes)
    upload_session_repo.mark_failed(db, session, error_message=reason)
    release_admission_slot(session.id, session.owner_id)


# ---------------------------------------------------------------------------
# Operaciones públicas
# ---------------------------------------------------------------------------

def initiate_upload(db: Session, current_user: User, payload: UploadInitiateRequest) -> UploadInitiateResponse:
    max_normal_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    max_large_bytes = settings.MAX_LARGE_UPLOAD_SIZE_MB * 1024 * 1024

    if payload.size_bytes <= max_normal_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Archivos de hasta {settings.MAX_UPLOAD_SIZE_MB}MB se suben por "
                f"POST /files/upload -- este camino es solo para archivos grandes"
            ),
        )
    if payload.size_bytes > max_large_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El archivo supera el tamaño máximo permitido ({settings.MAX_LARGE_UPLOAD_SIZE_MB} MB)",
        )

    original_name = (payload.file_name or "").strip() or "archivo"
    if len(original_name) > 255:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="El nombre no puede superar los 255 caracteres")

    target_folder_id: Optional[UUID] = None
    if payload.folder_id is not None:
        # Mismo criterio de ownership que `_get_target_parent_folder` en
        # app/files/router.py (reimplementado acá, no importado -- ver
        # docstring del módulo).
        folder = folder_repo.get_active(db, payload.folder_id)
        if not folder or folder.owner_id != current_user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Carpeta destino no encontrada")
        target_folder_id = folder.id

    client = get_internal_client()
    if client is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="El servicio de almacenamiento no está disponible")
    presign_client = _get_presign_client()
    if presign_client is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="El servicio de firma de subida no está disponible")

    # Reserva de cuota COMPLETA por adelantado -- reusa el service existente
    # (que a su vez usa `reserve_bytes_or_fail`, atómico, ver
    # app/storage_quota/repository.py). Levanta 413 sola si no alcanza.
    reserve_upload_bytes(db, current_user.id, payload.size_bytes)

    part_size = settings.LARGE_UPLOAD_PART_SIZE_BYTES
    part_count = max(1, math.ceil(payload.size_bytes / part_size))
    if part_count > _S3_MAX_PART_COUNT:
        release_upload_bytes(db, current_user.id, payload.size_bytes)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="El archivo requiere demasiadas partes con el tamaño de parte configurado",
        )

    session_id = uuid7()
    now = datetime.now(timezone.utc)
    session_expires_at = now + timedelta(hours=settings.UPLOAD_SESSION_EXPIRY_HOURS)

    if not _try_reserve_admission_slot(db, current_user.id, session_id):
        release_upload_bytes(db, current_user.id, payload.size_bytes)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demasiadas subidas grandes en curso, reintentá en unos segundos",
            headers={"Retry-After": "30"},
        )

    _, extension = os.path.splitext(original_name)
    bucket = settings.MINIO_PRIVATE_BUCKET
    _ensure_private_bucket(client, bucket)
    storage_key = f"files/{current_user.id}/{uuid7()}{extension}"

    try:
        create_resp = client.create_multipart_upload(
            Bucket=bucket,
            Key=storage_key,
            ContentType=payload.mime_type or "application/octet-stream",
        )
        minio_upload_id = create_resp["UploadId"]
    except Exception as exc:
        release_admission_slot(session_id, current_user.id)
        release_upload_bytes(db, current_user.id, payload.size_bytes)
        logger.error(f"[Uploads] create_multipart_upload falló para owner={current_user.id}: {exc}")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="No se pudo iniciar la subida en el almacenamiento") from exc

    session = UploadSession(
        id=session_id,
        owner_id=current_user.id,
        file_name=original_name,
        declared_size_bytes=payload.size_bytes,
        mime_type_declared=payload.mime_type or "application/octet-stream",
        target_folder_id=target_folder_id,
        storage_key=storage_key,
        minio_upload_id=minio_upload_id,
        part_size_bytes=part_size,
        part_count=part_count,
        status="in_progress",
        quota_reserved_bytes=payload.size_bytes,
        expires_at=session_expires_at,
    )
    try:
        db.add(session)
        db.commit()
        db.refresh(session)
    except Exception:
        db.rollback()
        release_admission_slot(session_id, current_user.id)
        release_upload_bytes(db, current_user.id, payload.size_bytes)
        try:
            client.abort_multipart_upload(Bucket=bucket, Key=storage_key, UploadId=minio_upload_id)
        except Exception:
            logger.warning(f"[Uploads] No se pudo abortar multipart tras fallo de DB (owner={current_user.id})")
        raise

    part_urls = _generate_part_urls(presign_client, bucket, storage_key, minio_upload_id, range(1, part_count + 1))

    return UploadInitiateResponse(
        upload_session_id=session.id,
        part_urls=part_urls,
        part_size_bytes=part_size,
        part_count=part_count,
        expires_at=now + timedelta(seconds=_PART_URL_EXPIRES_SECONDS),
    )


def refresh_part_urls(db: Session, current_user: User, session_id: UUID) -> RefreshPartUrlsResponse:
    session = upload_session_repo.get_owned(db, session_id, current_user.id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sesión de subida no encontrada")
    if session.status != "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"La sesión ya no está en curso (status='{session.status}')")

    client = get_internal_client()
    if client is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="El servicio de almacenamiento no está disponible")
    presign_client = _get_presign_client()
    if presign_client is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="El servicio de firma de subida no está disponible")

    bucket = settings.MINIO_PRIVATE_BUCKET

    # `ListParts` REAL -- nunca confiar en lo que el cliente dice que subió,
    # solo en lo que MinIO confirma que tiene. Pagina por las dudas (el
    # límite práctico de esta ronda, ~80 partes, nunca se acerca al límite
    # de 1000 por página de S3, pero es gratis cubrirlo).
    completed_parts: dict[int, CompletedPartOut] = {}
    part_number_marker = None
    while True:
        kwargs = {"Bucket": bucket, "Key": session.storage_key, "UploadId": session.minio_upload_id}
        if part_number_marker is not None:
            kwargs["PartNumberMarker"] = part_number_marker
        try:
            resp = client.list_parts(**kwargs)
        except Exception as exc:
            logger.error(f"[Uploads] list_parts falló para session={session_id}: {exc}")
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="No se pudo consultar el estado de la subida") from exc

        for part in resp.get("Parts", []):
            completed_parts[part["PartNumber"]] = CompletedPartOut(
                part_number=part["PartNumber"], etag=part["ETag"], size_bytes=int(part["Size"]),
            )
        if not resp.get("IsTruncated"):
            break
        part_number_marker = resp.get("NextPartNumberMarker")

    missing_part_numbers = [n for n in range(1, session.part_count + 1) if n not in completed_parts]
    part_urls = _generate_part_urls(presign_client, bucket, session.storage_key, session.minio_upload_id, missing_part_numbers)

    # El usuario sigue activo (pidió reanudar/refrescar) -- extiende el
    # lease corto de concurrencia, NO el plazo de 48hs de la sesión (ver
    # docstring del bloque de admisión). Best-effort: si esto falla, la
    # sesión sigue siendo válida, solo corre el riesgo de que su cupo de
    # concurrencia se pode antes de tiempo si nadie más la vuelve a tocar.
    _renew_admission_lease(session.id, session.owner_id)

    return RefreshPartUrlsResponse(
        part_urls=part_urls,
        completed_parts=sorted(completed_parts.values(), key=lambda p: p.part_number),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=_PART_URL_EXPIRES_SECONDS),
    )


def complete_upload(db: Session, current_user: User, session_id: UUID, payload: UploadCompleteRequest) -> FileModel:
    session = upload_session_repo.get_owned(db, session_id, current_user.id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sesión de subida no encontrada")
    if session.status != "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"La sesión ya no está en curso (status='{session.status}')")

    client = get_internal_client()
    if client is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="El servicio de almacenamiento no está disponible")

    bucket = settings.MINIO_PRIVATE_BUCKET
    parts_payload = sorted(
        ({"PartNumber": p.part_number, "ETag": p.etag} for p in payload.parts),
        key=lambda p: p["PartNumber"],
    )

    try:
        client.complete_multipart_upload(
            Bucket=bucket,
            Key=session.storage_key,
            UploadId=session.minio_upload_id,
            MultipartUpload={"Parts": parts_payload},
        )
    except Exception as exc:
        logger.error(f"[Uploads] complete_multipart_upload falló para session={session_id}: {exc}")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="No se pudo completar la subida -- verificá que todas las partes se hayan subido correctamente",
        ) from exc

    try:
        head = client.head_object(Bucket=bucket, Key=session.storage_key)
        actual_size = int(head["ContentLength"])
    except Exception as exc:
        logger.error(f"[Uploads] head_object post-complete falló para session={session_id}: {exc}")
        _fail_after_complete(db, session, client, bucket, reason="No se pudo verificar el tamaño real tras completar la subida")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="No se pudo verificar la subida completada") from exc

    if actual_size > session.quota_reserved_bytes:
        # El cliente declaró (y reservó cuota por) menos de lo que
        # realmente subió -- el objeto YA está completo en MinIO (no se
        # puede "abortar" un multipart ya completado), así que se borra en
        # vez de dejarlo huérfano ocupando espacio sin cuota que lo
        # respalde. Decisión de diseño explícita, no 100% especificada en
        # el encargo -- ver reporte final del agente.
        _fail_after_complete(
            db, session, client, bucket,
            reason=f"Tamaño real ({actual_size}) superó la cuota reservada ({session.quota_reserved_bytes})",
        )
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="El tamaño real subido superó el tamaño declarado -- la subida fue rechazada")

    if actual_size < session.quota_reserved_bytes:
        # Libera la diferencia -- la cuota debe reflejar uso REAL, no el
        # techo declarado originalmente (ver docstring de
        # `UploadSession.quota_reserved_bytes`).
        release_upload_bytes(db, current_user.id, session.quota_reserved_bytes - actual_size)

    db_file = FileModel(
        name=session.file_name,
        folder_id=session.target_folder_id,
        owner_id=session.owner_id,
        storage_key=session.storage_key,
        size_bytes=actual_size,
        mime_type=session.mime_type_declared,
        scan_status="pending",
    )
    db.add(db_file)
    db.flush()

    db.add(
        FileVersion(
            file_id=db_file.id,
            version_number=1,
            storage_key=session.storage_key,
            size_bytes=actual_size,
            mime_type=session.mime_type_declared,
            created_by_id=current_user.id,
        )
    )

    # Mismo `db.commit()` que File/FileVersion -- a propósito se setean los
    # campos de la sesión directo acá (no vía un método de repository que
    # comitee por su cuenta, como sí hacen `mark_aborted`/`mark_failed`):
    # las tres filas (File, FileVersion, UploadSession) tienen que quedar
    # confirmadas juntas o ninguna, para que un crash a mitad de camino
    # nunca deje un File "huérfano" sin su sesión marcada, ni una sesión
    # marcada 'completed_pending_scan' sin el File que dice tener.
    session.status = "completed_pending_scan"
    session.file_id = db_file.id
    session.quota_reserved_bytes = actual_size
    db.add(session)
    db.commit()
    db.refresh(db_file)

    release_admission_slot(session.id, session.owner_id)
    _enqueue_av_scan(db_file.id)

    return db_file


def abort_upload(db: Session, current_user: User, session_id: UUID) -> UploadSession:
    session = upload_session_repo.get_owned(db, session_id, current_user.id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sesión de subida no encontrada")
    if session.status != "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"La sesión ya no está en curso (status='{session.status}')")

    client = get_internal_client()
    if client is not None:
        try:
            client.abort_multipart_upload(Bucket=settings.MINIO_PRIVATE_BUCKET, Key=session.storage_key, UploadId=session.minio_upload_id)
        except Exception as exc:
            # Best-effort -- si MinIO ya no tiene ese multipart (ej. vencido
            # del lado de MinIO por su propia política de lifecycle, si
            # hubiera una configurada), igual liberamos cuota y marcamos
            # 'aborted' -- lo importante es que ESTE lado (cuota, admisión,
            # estado de la sesión) quede consistente.
            logger.warning(f"[Uploads] abort_multipart_upload falló para session={session_id} (se continúa): {exc}")

    release_upload_bytes(db, current_user.id, session.quota_reserved_bytes)
    session = upload_session_repo.mark_aborted(db, session)
    release_admission_slot(session.id, session.owner_id)
    return session
