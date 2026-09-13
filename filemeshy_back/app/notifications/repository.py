from uuid import UUID
"""
CRUD operations para Notification
"""

from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from datetime import datetime

from app.notifications.models import Notification
from app.notifications.schemas import NotificationCreate


class CRUDNotification:
    """Operaciones CRUD para notificaciones."""

    def get(self, db: Session, notification_id: UUID) -> Optional[Notification]:
        """Obtener notificación por ID."""
        return db.query(Notification).filter(Notification.id == notification_id).first()

    def get_by_user(
        self,
        db: Session,
        user_id: UUID,
        skip: int = 0,
        limit: int = 20,
        unread_only: bool = False,
        notification_type: Optional[str] = None,
    ) -> Tuple[List[Notification], int]:
        """
        Obtener notificaciones de un usuario con paginación.
        Retorna (lista_notificaciones, total).
        """
        query = db.query(Notification).filter(Notification.user_id == user_id)

        if unread_only:
            query = query.filter(Notification.is_read == False)

        if notification_type:
            query = query.filter(Notification.type == notification_type)

        total = query.count()
        items = query.order_by(desc(Notification.created_at)).offset(skip).limit(limit).all()

        return items, total

    def get_unread_count(self, db: Session, user_id: UUID) -> int:
        """Obtener cantidad de notificaciones no leídas."""
        return db.query(Notification).filter(
            and_(
                Notification.user_id == user_id,
                Notification.is_read == False,
            )
        ).count()

    def create(self, db: Session, obj_in: NotificationCreate) -> Notification:
        """Crear nueva notificación."""
        db_obj = Notification(
            user_id=obj_in.user_id,
            title=obj_in.title,
            message=obj_in.message,
            type=obj_in.type,
            severity=obj_in.severity,
            action_url=obj_in.action_url,
            extra_data=obj_in.extra_data,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def mark_as_read(self, db: Session, notification_id: UUID, user_id: UUID) -> Optional[Notification]:
        """Marcar una notificación como leída."""
        db_obj = db.query(Notification).filter(
            and_(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        ).first()

        if db_obj and not db_obj.is_read:
            db_obj.is_read = True
            db_obj.read_at = datetime.utcnow()
            db.commit()
            db.refresh(db_obj)

        return db_obj

    def mark_all_as_read(self, db: Session, user_id: UUID) -> int:
        """Marcar todas las notificaciones del usuario como leídas. Retorna cantidad actualizada."""
        now = datetime.utcnow()
        count = db.query(Notification).filter(
            and_(
                Notification.user_id == user_id,
                Notification.is_read == False,
            )
        ).update({"is_read": True, "read_at": now})
        db.commit()
        return count

    def delete(self, db: Session, notification_id: UUID, user_id: UUID) -> bool:
        """Eliminar una notificación (solo si pertenece al usuario)."""
        db_obj = db.query(Notification).filter(
            and_(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        ).first()

        if db_obj:
            db.delete(db_obj)
            db.commit()
            return True
        return False

    def delete_all_read(self, db: Session, user_id: UUID) -> int:
        """Eliminar todas las notificaciones leídas del usuario. Retorna cantidad eliminada."""
        count = db.query(Notification).filter(
            and_(
                Notification.user_id == user_id,
                Notification.is_read == True,
            )
        ).delete()
        db.commit()
        return count


notification = CRUDNotification()
