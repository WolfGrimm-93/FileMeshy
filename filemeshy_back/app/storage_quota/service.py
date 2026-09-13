"""Servicio de cuotas de almacenamiento: chequeo+reserva de límite (llamado
desde `app.files.router.upload_file`) y lectura de capacidad real de disco
del volumen de MinIO vía su Admin API (sin SDK dedicado, ver
`get_disk_capacity`).
"""

import hashlib
import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.storage_quota.repository import user_storage_quota_repo

logger = logging.getLogger(__name__)


def reserve_upload_bytes(db: Session, user_id: UUID, additional_bytes: int) -> None:
    """Bloquea con 413 si subir `additional_bytes` más superaría el límite
    asignado al usuario -- si NO bloquea, ya reservó ese cupo (sumado a
    `bytes_used`) en la misma operación atómica que lo chequeó (ver
    app/storage_quota/repository.py::reserve_bytes_or_fail). Llamar ANTES de
    subir a MinIO.

    Chequeo y reserva son un único UPDATE con guard, no un SELECT seguido de
    un UPDATE aparte -- con dos pasos separados, dos uploads concurrentes del
    mismo usuario pueden pasar el chequeo cada uno por su lado (los dos ven
    el mismo remanente) y sumados superar el límite (hallazgo de la revisión
    adversarial, Fase 3, 2026-09-08).

    Si la subida a MinIO falla DESPUÉS de reservar, el caller tiene que
    liberar la reserva con `release_upload_bytes` -- esta función no sabe si
    la subida tuvo éxito."""
    if not user_storage_quota_repo.reserve_bytes_or_fail(db, user_id, additional_bytes):
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Se alcanzó el límite de almacenamiento asignado",
        )


def release_upload_bytes(db: Session, user_id: UUID, bytes_to_release: int) -> None:
    """Compensa una reserva de `reserve_upload_bytes` cuando la subida a
    MinIO falla después de reservar -- si no se libera, el contador queda
    inflado por un archivo que nunca llegó a existir. Ver
    app/files/router.py::upload_file."""
    user_storage_quota_repo.adjust_bytes_used(db, user_id, -bytes_to_release)


# ---------------------------------------------------------------------------
# Capacidad real de disco -- Admin API de MinIO firmada con SigV4
# ---------------------------------------------------------------------------
# MinIO no expone espacio usado/libre del volumen vía la API de objetos (S3),
# solo vía su Admin API (endpoint HTTP propio, no S3). No hay SDK Python de
# admin (madmin-go es Go-only) y agregar una dependencia nueva para esto no
# está justificado: el Admin API firma sus requests con el MISMO esquema
# SigV4 que boto3 ya trae (botocore), así que se firma a mano reusando
# botocore.auth.SigV4Auth -- confirmado contra un MinIO real (contenedor
# descartable) probando ambas variantes hasta encontrar la combinación
# correcta:
#   - servicio de firma "s3" (no "execute-api" ni ningún nombre propio de
#     admin), igual que cualquier request S3 normal.
#   - header `X-Amz-Content-Sha256` (hash del body, vacío en un GET) tiene
#     que estar PRESENTE y firmado -- sin él, MinIO devuelve 403 AccessDenied
#     aunque el resto de la firma sea correcto (a diferencia del cliente S3
#     normal, donde boto3/botocore no lo agrega para requests que no son de
#     S3). Confirmado con el cliente real minio-go/madmin-go (fuente:
#     pkg/signer/request-signature-v4.go y madmin-go/api.go): calculan y
#     setean ese header ANTES de firmar.
#   - la región no importa (probado con "" y "us-east-1", los dos autentican
#     igual) -- se usa "us-east-1" acá por consistencia con el resto del
#     proyecto (ver app/files/service.py::_get_client).
#   - path fijo `/minio/admin/v3/info` (prefijo `/minio/admin` + `/v3/info`,
#     igual que arma madmin-go en `makeTargetURL`).
_MINIO_ADMIN_INFO_PATH = "/minio/admin/v3/info"


def get_disk_capacity() -> dict:
    """Lee `total_bytes`/`used_bytes`/`free_bytes` reales del volumen de
    MinIO sumando el espacio de todos los discos "ok" que reporta
    `GET /minio/admin/v3/info`. Nunca lanza excepción -- cualquier fallo
    (MinIO no configurado, Admin API no accesible, respuesta inesperada)
    se loggea y devuelve los tres campos en `None`."""
    empty = {"total_bytes": None, "used_bytes": None, "free_bytes": None}

    from app.core.config import settings

    if not settings.MINIO_ENDPOINT or not settings.MINIO_ACCESS_KEY or not settings.MINIO_SECRET_KEY:
        logger.info("[StorageQuota] MinIO no configurado -- capacidad de disco no disponible")
        return empty

    try:
        import httpx
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest
        from botocore.credentials import Credentials

        url = f"{settings.MINIO_ENDPOINT.rstrip('/')}{_MINIO_ADMIN_INFO_PATH}"
        empty_sha256 = hashlib.sha256(b"").hexdigest()

        request = AWSRequest(
            method="GET",
            url=url,
            data=b"",
            headers={"X-Amz-Content-Sha256": empty_sha256},
        )
        creds = Credentials(settings.MINIO_ACCESS_KEY, settings.MINIO_SECRET_KEY)
        SigV4Auth(creds, "s3", "us-east-1").add_auth(request)

        response = httpx.get(url, headers=dict(request.headers), timeout=10.0)
        response.raise_for_status()
        info = response.json()
    except Exception as e:
        logger.warning(f"[StorageQuota] Error consultando capacidad de disco en MinIO Admin API: {e}")
        return empty

    total_bytes = 0
    used_bytes = 0
    free_bytes = 0
    found_any_drive = False
    for server in info.get("servers", []):
        for drive in server.get("drives", []):
            if drive.get("state") != "ok":
                continue
            found_any_drive = True
            total_bytes += drive.get("totalspace") or 0
            used_bytes += drive.get("usedspace") or 0
            free_bytes += drive.get("availspace") or 0

    if not found_any_drive:
        logger.warning("[StorageQuota] MinIO Admin API no devolvió discos 'ok' -- capacidad no disponible")
        return empty

    return {"total_bytes": total_bytes, "used_bytes": used_bytes, "free_bytes": free_bytes}
