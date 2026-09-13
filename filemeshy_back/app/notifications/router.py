"""
Router de Notificaciones
Endpoints para gestionar notificaciones del usuario autenticado.
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
import math

from app.core.database import get_db
from app.auth.service import get_current_active_user
from app.users.models import User
from app.notifications.schemas import (
    NotificationResponse,
    NotificationListResponse,
    UnreadCountResponse,
)
from app.notifications.repository import notification as crud_notification


router = APIRouter()


@router.get("", response_model=NotificationListResponse)
async def get_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Obtener notificaciones del usuario autenticado con paginación.

    Parámetros:
    - page: Número de página (desde 1)
    - page_size: Cantidad por página (máximo 100)
    - unread_only: Solo no leídas
    - type: Filtrar por tipo (stock_bajo, pago_vencido, nueva_venta, seguridad, sistema)
    """
    skip = (page - 1) * page_size

    items, total = crud_notification.get_by_user(
        db,
        user_id=current_user.id,
        skip=skip,
        limit=page_size,
        unread_only=unread_only,
        notification_type=type,
    )

    unread_count = crud_notification.get_unread_count(db, current_user.id)
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return NotificationListResponse(
        items=items,
        total=total,
        unread_count=unread_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Obtener cantidad de notificaciones no leídas."""
    count = crud_notification.get_unread_count(db, current_user.id)
    return UnreadCountResponse(unread_count=count)


@router.put("/read-all", response_model=dict)
async def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Marcar todas las notificaciones como leídas."""
    count = crud_notification.mark_all_as_read(db, current_user.id)
    return {"message": f"Se marcaron {count} notificaciones como leídas", "count": count}


@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Obtener una notificación específica."""
    notif = crud_notification.get(db, notification_id)

    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificación no encontrada"
        )

    if notif.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver esta notificación"
        )

    return notif


@router.put("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Marcar una notificación como leída."""
    notif = crud_notification.mark_as_read(db, notification_id, current_user.id)

    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificación no encontrada"
        )

    return notif


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Eliminar una notificación."""
    deleted = crud_notification.delete(db, notification_id, current_user.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificación no encontrada"
        )

    return None


@router.delete("", response_model=dict)
async def delete_read_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Eliminar todas las notificaciones leídas."""
    count = crud_notification.delete_all_read(db, current_user.id)
    return {"message": f"Se eliminaron {count} notificaciones leídas", "count": count}
