"""Router de cuotas de almacenamiento -- pantalla admin (Hito 3).

Router-heavy por convención del proyecto (ver notifications/access_control/
files): la lógica de listado y upsert vive acá, `repository.py` solo hace
queries/statements. `service.py` queda aparte porque sus dos funciones
(`check_quota_or_raise`, `get_disk_capacity`) las usan otros módulos
(files.router, worker.tasks.maintenance), no solo este router.
"""

import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.access_control.service import has_permission
from app.auth.service import get_current_active_user
from app.core.database import get_db
from app.storage_quota.repository import user_storage_quota_repo
from app.storage_quota.schemas import (
    StorageCapacityResponse,
    StorageQuotaItem,
    StorageQuotaListResponse,
    StorageQuotaUpdate,
)
from app.storage_quota.service import get_disk_capacity
from app.users.models import User

router = APIRouter(prefix="/storage-quotas", tags=["storage-quotas"])


class StorageQuotaMeResponse(BaseModel):
    """Schema local al router (mismo criterio que configuration/router.py
    para schemas de un solo endpoint) -- storage_quota/schemas.py queda fuera
    del alcance de este fix puntual."""
    limit_bytes: Optional[int] = None
    bytes_used: int = 0


def _to_item(user: User, quota) -> StorageQuotaItem:
    """`quota` puede ser None -- usuario sin fila de cuota todavía (nunca se
    le configuró límite, ver storage_quota/service.py::check_quota_or_raise).
    `last_name` es nullable en `users`; se normaliza a cadena vacía porque el
    contrato de este endpoint no expone `null` para ese campo."""
    return StorageQuotaItem(
        user_id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name or "",
        limit_bytes=quota.limit_bytes if quota else None,
        bytes_used=quota.bytes_used if quota else 0,
    )


@router.get("", response_model=StorageQuotaListResponse)
@router.get("/", response_model=StorageQuotaListResponse)
def list_storage_quotas(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["storage_quotas.view"])),
):
    """Lista usuarios + su cuota, LEFT JOIN contra `user_storage_quotas` --
    un usuario sin fila propia igual aparece (sin límite, 0 bytes usados).
    Mismo criterio de paginación/búsqueda que `GET /users` (ver
    app/users/router.py::list_users)."""
    from sqlalchemy import func

    from app.storage_quota.models import UserStorageQuota

    query = db.query(User, UserStorageQuota).outerjoin(
        UserStorageQuota, UserStorageQuota.user_id == User.id
    )

    if search:
        search_term = f"%{search}%"
        full_name = func.concat(User.first_name, ' ', func.coalesce(User.last_name, ''))
        query = query.filter(
            (User.first_name.ilike(search_term))
            | (User.last_name.ilike(search_term))
            | (User.email.ilike(search_term))
            | (full_name.ilike(search_term))
        )

    total = query.count()
    rows = query.order_by(User.email.asc()).offset(skip).limit(limit).all()
    items = [_to_item(user, quota) for user, quota in rows]

    page = (skip // limit) + 1 if limit > 0 else 1
    total_pages = math.ceil(total / limit) if limit > 0 else 0

    return StorageQuotaListResponse(
        items=items, total=total, page=page, page_size=limit, total_pages=total_pages
    )


@router.get("/capacity", response_model=StorageCapacityResponse)
def get_storage_capacity(
    current_user: User = Depends(has_permission(["storage_quotas.view"])),
):
    """Capacidad real de disco del volumen de MinIO (todos los campos en
    `null` si no se pudo leer -- ver service.py::get_disk_capacity)."""
    return StorageCapacityResponse(**get_disk_capacity())


@router.get("/me", response_model=StorageQuotaMeResponse)
def get_my_storage_quota(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Cuota de almacenamiento del usuario autenticado -- a diferencia del
    resto de este router (storage_quotas.view/manage), NO requiere permiso
    admin: cualquier usuario puede ver SU PROPIA cuota. Nunca acepta un
    `user_id` de otro usuario -- siempre lee `current_user.id`, así que no
    hay forma de pedir la cuota de otra persona por acá."""
    quota = user_storage_quota_repo.get_by_user_id(db, current_user.id)
    return StorageQuotaMeResponse(
        limit_bytes=quota.limit_bytes if quota else None,
        bytes_used=quota.bytes_used if quota else 0,
    )


@router.put("/{user_id}", response_model=StorageQuotaItem)
def update_storage_quota(
    user_id: UUID,
    payload: StorageQuotaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["storage_quotas.manage"])),
):
    """Upsert del límite de un usuario. `limit_bytes: null` = sin límite."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    if payload.limit_bytes is not None and payload.limit_bytes < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El límite no puede ser negativo",
        )

    quota = user_storage_quota_repo.upsert_limit(db, user_id, payload.limit_bytes)
    return _to_item(user, quota)
