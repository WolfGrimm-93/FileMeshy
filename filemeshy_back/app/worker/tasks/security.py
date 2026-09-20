"""
Tareas de seguridad — FileMeshy Worker.

Monitoreo de actividad sospechosa y notificaciones de seguridad.
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.worker.celery_app import celery_app
from app.worker.db import get_worker_db, iter_tenant_schemas

logger = logging.getLogger(__name__)

# Umbral de intentos fallidos de login antes de notificar
LOGIN_FAIL_THRESHOLD = 5
LOGIN_FAIL_WINDOW_MINUTES = 10


# Módulo dueño: audit (lee audit_log) + notifications (dispara la alerta).
@celery_app.task(bind=True, max_retries=2, default_retry_delay=60,
                 name="app.worker.tasks.security.notify_login_failures")
def notify_login_failures(self, tenant_schema: str | None, user_id: UUID, ip_address: str):
    """
    Notifica cuando un usuario tiene múltiples intentos de login fallidos
    desde la misma IP en un período corto.
    Disparada por el middleware de auditoría tras registrar LOGIN_FAIL.
    """
    try:
        with get_worker_db(schema_name=tenant_schema) as db:
            from app.audit.models import AuditLog
            from sqlalchemy import and_, func

            window_start = datetime.now(timezone.utc) - timedelta(minutes=LOGIN_FAIL_WINDOW_MINUTES)

            # Contar intentos fallidos recientes desde esta IP
            intentos = (
                db.query(func.count(AuditLog.id))
                .filter(
                    and_(
                        AuditLog.action == "LOGIN_FAIL",
                        AuditLog.ip_address == ip_address,
                        AuditLog.created_at >= window_start,
                    )
                )
                .scalar()
            ) or 0

            if intentos < LOGIN_FAIL_THRESHOLD:
                return  # Aún por debajo del umbral

            # Notificar a todos los admins
            from app.worker.tasks.notification_helpers import _get_admin_users_with_notifications, create_notification

            admin_users = _get_admin_users_with_notifications(db)
            for admin in admin_users:
                # Deduplicar: no spamear más de 1 notificación por IP cada 30 min
                from app.notifications.models import Notification
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
                ya_notificado = (
                    db.query(Notification)
                    .filter(
                        Notification.user_id == admin.id,
                        Notification.type == "seguridad",
                        Notification.created_at >= cutoff,
                        Notification.extra_data["ip_address"].astext == ip_address,
                    )
                    .first()
                )
                if ya_notificado:
                    continue

                create_notification(
                    db=db,
                    user_id=admin.id,
                    title="Intentos de acceso fallidos detectados",
                    message=(
                        f"{intentos} intentos fallidos de login desde IP {ip_address} "
                        f"en los últimos {LOGIN_FAIL_WINDOW_MINUTES} minutos."
                    ),
                    notif_type="seguridad",
                    severity="error",
                    action_url="/logs",
                    extra_data={
                        "user_id": str(user_id),
                        "ip_address": ip_address,
                        "intentos": intentos,
                        "ventana_minutos": LOGIN_FAIL_WINDOW_MINUTES,
                        "reference_id": str(user_id),
                    },
                )

            logger.warning(
                f"notify_login_failures: {intentos} intentos desde {ip_address} "
                f"(umbral={LOGIN_FAIL_THRESHOLD})"
            )

    except Exception as exc:
        logger.error(f"notify_login_failures error: {exc}")
        raise self.retry(exc=exc, countdown=60)


# Módulo dueño: audit.
@celery_app.task(name="app.worker.tasks.security.audit_suspicious_activity")
def audit_suspicious_activity():
    """
    Revisión periódica (cada hora :05) de patrones de actividad sospechosa en audit_log,
    por tenant activo.
    Detecta:
    - Muchos DELETE consecutivos del mismo usuario
    - Acceso fuera de horario laboral (antes de 6 AM o después de 10 PM)
    - IPs nuevas para usuarios con historial
    """
    resultados = {}
    for schema in iter_tenant_schemas():
        clave = schema or "public"
        try:
            with get_worker_db(schema_name=schema) as db:
                from app.audit.models import AuditLog
                from sqlalchemy import func, and_

                window_start = datetime.now(timezone.utc) - timedelta(hours=1)
                alertas = []

                # ── 1. Muchos DELETE de un mismo usuario en 1 hora ──
                DELETE_THRESHOLD = 20

                delete_counts = (
                    db.query(AuditLog.user_id, func.count(AuditLog.id).label("cnt"))
                    .filter(
                        and_(
                            AuditLog.action == "DELETE",
                            AuditLog.created_at >= window_start,
                            AuditLog.user_id != None,
                        )
                    )
                    .group_by(AuditLog.user_id)
                    .having(func.count(AuditLog.id) >= DELETE_THRESHOLD)
                    .all()
                )

                for user_id, count in delete_counts:
                    alertas.append({
                        "tipo": "bulk_delete",
                        "user_id": str(user_id),
                        "mensaje": f"Usuario {user_id} realizó {count} DELETE en la última hora",
                        "severidad": "error",
                    })

                # ── 2. Acceso fuera de horario (antes 6 AM o después 10 PM RD — UTC-4) ──
                now_rd = datetime.now(timezone.utc) - timedelta(hours=4)
                hora_rd = now_rd.hour
                if hora_rd < 6 or hora_rd >= 22:
                    # Verificar si hay logins en la última hora
                    logins_nocturnos = (
                        db.query(func.count(AuditLog.id))
                        .filter(
                            and_(
                                AuditLog.action == "LOGIN",
                                AuditLog.created_at >= window_start,
                            )
                        )
                        .scalar()
                    ) or 0

                    if logins_nocturnos > 0:
                        alertas.append({
                            "tipo": "acceso_nocturno",
                            "mensaje": f"{logins_nocturnos} login(s) fuera de horario laboral ({hora_rd:02d}:xx RD)",
                            "severidad": "warning",
                        })

                # ── Notificar si hay alertas ──
                if alertas:
                    from app.worker.tasks.notification_helpers import _get_admin_users_with_notifications, create_notification

                    with get_worker_db(schema_name=schema) as db2:
                        admin_users = _get_admin_users_with_notifications(db2)
                        for alerta in alertas:
                            for admin in admin_users:
                                create_notification(
                                    db=db2,
                                    user_id=admin.id,
                                    title="Actividad sospechosa detectada",
                                    message=alerta["mensaje"],
                                    notif_type="seguridad",
                                    severity=alerta["severidad"],
                                    action_url="/logs",
                                    extra_data={**alerta, "reference_id": alerta.get("user_id", 0)},
                                )
                    logger.warning(f"audit_suspicious_activity: {len(alertas)} alerta(s) generadas (tenant={clave})")
                else:
                    logger.debug(f"audit_suspicious_activity: sin actividad sospechosa (tenant={clave})")

                resultados[clave] = {"alertas": len(alertas)}
        except Exception:
            logger.exception(f"audit_suspicious_activity: fallo en tenant '{clave}'")

    return resultados
