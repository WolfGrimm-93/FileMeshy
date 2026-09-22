"""Router de subida multipart directa cliente→MinIO (Ronda 9).

`prefix="/uploads"`, montado en `app/api/v1/router.py` junto al resto de
routers de la app -- misma autenticación JWT normal que cualquier feature de
usuario (`has_permission(["files.upload"])`, el mismo permiso que ya exige
`POST /files/upload`) -- a diferencia del panel de administración de tenants
de Ronda 8, esto NO es un endpoint de plataforma, es una feature normal para
cualquier usuario autenticado con permiso de subir archivos.

Toda la lógica vive en `app/uploads/service.py` (router-heavy por convención
del proyecto, ver `app/backups/router.py`) -- acá solo se resuelve la
dependencia de auth y se llama al service."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.access_control.service import has_permission
from app.core.database import get_db
from app.files.schemas import FileOut
from app.uploads.schemas import (
    RefreshPartUrlsResponse,
    UploadCompleteRequest,
    UploadInitiateRequest,
    UploadInitiateResponse,
    UploadSessionOut,
)
from app.uploads.service import abort_upload, complete_upload, initiate_upload, refresh_part_urls
from app.users.models import User

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("/initiate", response_model=UploadInitiateResponse, status_code=status.HTTP_201_CREATED)
def initiate(
    payload: UploadInitiateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.upload"])),
):
    """Arranca una sesión de subida multipart para un archivo GRANDE (más de
    `settings.MAX_UPLOAD_SIZE_MB`, hasta `settings.MAX_LARGE_UPLOAD_SIZE_MB`).
    Reserva cuota completa por adelantado, crea el multipart real en MinIO y
    devuelve una URL presignada por parte -- el navegador sube cada parte
    DIRECTO a MinIO (vía el proxy nginx público), los bytes nunca pasan por
    este proceso."""
    return initiate_upload(db, current_user, payload)


@router.post("/{session_id}/refresh-part-urls", response_model=RefreshPartUrlsResponse)
def refresh(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.upload"])),
):
    """Reanuda una sesión vieja cuyas URLs presignadas ya vencieron: consulta
    `ListParts` REAL contra MinIO para saber qué partes ya están confirmadas
    (con su ETag, para no resubirlas) y devuelve URLs nuevas solo para las
    que faltan. De paso, renueva el lease corto de admisión de concurrencia
    de la sesión (`settings.LARGE_UPLOAD_ADMISSION_LEASE_HOURS`) -- llamar a
    este endpoint es la señal de que el usuario sigue activo."""
    return refresh_part_urls(db, current_user, session_id)


@router.post("/{session_id}/complete", response_model=FileOut)
def complete(
    session_id: UUID,
    payload: UploadCompleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.upload"])),
):
    """Cierra el multipart real en MinIO y crea el `File` (con
    `scan_status='pending'`, invisible hasta que el escaneo asíncrono de AV
    lo marque `'clean'`) -- la respuesta trae ese estado tal cual para que el
    frontend muestre "procesando"."""
    return complete_upload(db, current_user, session_id, payload)


@router.post("/{session_id}/abort", response_model=UploadSessionOut)
def abort(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.upload"])),
):
    """Aborta el multipart real en MinIO y libera la cuota reservada -- para
    que el usuario cancele una subida en curso a propósito (a diferencia de
    una sesión simplemente abandonada, que limpia sola la tarea periódica de
    `app/worker/tasks/uploads.py`)."""
    return abort_upload(db, current_user, session_id)
