"""
Helpers genéricos de notificaciones — compartidos entre
worker/tasks/notifications.py y worker/tasks/security.py.
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Mapeo: notif_type (backend) → clave en la config de tipos del admin.
# Hoy no queda ningún tipo con control admin configurable (todos se crean
# siempre); el mapeo queda listo por si un tipo futuro lo necesita.
_NOTIF_TYPE_CONFIG_KEY: dict[str, str | None] = {}

_DEFAULT_NOTIF_TYPES: dict[str, dict] = {}


def _get_type_settings(db: Session, notif_type: str) -> dict | None:
    """
    Retorna {'email': bool, 'sistema': bool} para el notif_type dado.
    Retorna None si el tipo no tiene control admin (siempre se crea).
    """
    config_key = _NOTIF_TYPE_CONFIG_KEY.get(notif_type)
    if config_key is None:
        return None

    from app.configuration.repository import crud_system_configuration
    config = crud_system_configuration.get_by_key(db, "notification_types")
    types_cfg = config.value_json if (config and config.value_json) else _DEFAULT_NOTIF_TYPES
    return types_cfg.get(config_key, _DEFAULT_NOTIF_TYPES.get(config_key, {"email": True, "sistema": True}))


def _get_admin_users_with_notifications(db: Session) -> list:
    """Retorna usuarios ADMIN/SUPER_ADMIN con system_notifications=True."""
    from app.users.models import User
    from app.access_control.models import Role
    from app.configuration.repository import crud_user_preferences

    admin_users = (
        db.query(User)
        .join(User.role_obj)
        .filter(
            User.is_active == True,
            Role.name.in_(["ADMIN", "SUPER_ADMIN"]),
        )
        .all()
    )

    result = []
    for user in admin_users:
        try:
            prefs = crud_user_preferences.get_or_create(db, str(user.id))
            if prefs.system_notifications:
                result.append(user)
        except Exception:
            pass
    return result


def _is_duplicate(db: Session, user_id: UUID, notif_type: str, reference_id: UUID, hours: int = 4) -> bool:
    """
    Deduplicación inteligente de notificaciones:

    1. Si existe una notificación NO LEÍDA del mismo tipo y referencia → siempre duplicado,
       sin importar cuándo fue creada. El problema sigue activo y el usuario no la ha visto.

    2. Si existe una notificación LEÍDA del mismo tipo y referencia creada en las últimas
       N horas → duplicado (evita re-generar inmediatamente después de que el usuario la leyó).

    3. Si la notificación fue LEÍDA y ya pasaron las N horas → no es duplicado, se puede
       re-generar (el problema persiste y el usuario ya tuvo tiempo de verlo).
    """
    from app.notifications.models import Notification
    from sqlalchemy import and_, or_

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    base_filter = and_(
        Notification.user_id == user_id,
        Notification.type == notif_type,
        Notification.extra_data["reference_id"].as_string() == str(reference_id),
    )

    exists = (
        db.query(Notification)
        .filter(
            base_filter,
            or_(
                # Caso 1: no leída → siempre bloquear
                Notification.is_read == False,
                # Caso 2: leída pero dentro de la ventana de tiempo → bloquear
                and_(
                    Notification.is_read == True,
                    Notification.created_at >= cutoff,
                ),
            ),
        )
        .first()
    )
    return exists is not None


def create_notification(db: Session, user_id: UUID, title: str, message: str,
                         notif_type: str, severity: str, action_url: str = None,
                         extra_data: dict = None, send_email: bool = True) -> bool:
    """
    Crea una notificación en BD y despacha email al usuario si tiene
    email_notifications=True en sus preferencias Y el tipo tiene email habilitado.
    Retorna True si se creó, False si el tipo está deshabilitado o hubo error.
    `send_email=False` (Ronda 12d): no despacha el email de la notificación (el caller manda
    su propio email y no queremos dos).

    Pública (antes `_create_notification`) -- la llaman también módulos
    fuera de `worker/tasks` (ver app/storage_quota/service.py, notificación
    de cuota cerca del límite), no solo otras tasks del worker.
    """
    from app.notifications.repository import notification as crud_notification
    from app.notifications.schemas import NotificationCreate, NotificationType, NotificationSeverity

    # Verificar configuración de tipo: ¿sistema habilitado para este evento?
    type_settings = _get_type_settings(db, notif_type)
    if type_settings is not None and not type_settings.get("sistema", True):
        return False  # El admin desactivó este tipo para el canal sistema

    try:
        notif = crud_notification.create(db, NotificationCreate(
            user_id=user_id,
            title=title,
            message=message,
            type=NotificationType(notif_type),
            severity=NotificationSeverity(severity),
            action_url=action_url,
            extra_data=extra_data or {},
        ))

        # Despachar email si el usuario quiere emails Y el tipo tiene email habilitado
        email_for_type = type_settings.get("email", True) if type_settings is not None else True
        if email_for_type and send_email:
            try:
                from app.configuration.repository import crud_user_preferences
                from app.core.database import tenant_schema_ctx
                from app.worker.tasks.email import send_notification_email
                prefs = crud_user_preferences.get_or_create(db, str(user_id))
                if prefs and prefs.email_notifications:
                    # Capturado acá porque este helper corre dentro del `with
                    # get_worker_db(schema_name=...)` del task padre -- el
                    # ContextVar todavía apunta al schema correcto.
                    send_notification_email.delay(tenant_schema_ctx.get(), user_id, notif.id)
            except Exception as e:
                logger.warning(f"No se pudo despachar email notif user={user_id}: {e}")

        return True
    except Exception as e:
        logger.error(f"Error creando notificación tipo={notif_type} user={user_id}: {e}")
        # Ronda 12d: sin rollback la sesión quedaba en estado "pending rollback" y el siguiente
        # acceso ORM del caller (p. ej. `user.email`) lanzaba PendingRollbackError (500).
        try:
            db.rollback()
        except Exception:
            pass
        return False
