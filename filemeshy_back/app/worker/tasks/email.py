"""
Tareas de email — FileMeshy Worker.

Todas las tareas de envío de email van en la cola 'emails'
para aplicar rate limiting de forma independiente.
"""

import logging
from uuid import UUID

from app.worker.celery_app import celery_app
from app.worker.db import get_worker_db
from app.core.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120,
                 name="app.worker.tasks.email.send_notification_email",
                 queue="emails")
def send_notification_email(self, tenant_schema: str | None, user_id: UUID, notification_id: UUID):
    """
    Envía un email al usuario sobre una notificación específica.
    Se dispara cuando el usuario tiene email_notifications=True.
    """
    try:
        with get_worker_db(schema_name=tenant_schema) as db:
            from app.users.models import User
            from app.notifications.models import Notification
            from app.notifications.service import EmailService

            user = db.query(User).filter(User.id == user_id).first()
            notif = db.query(Notification).filter(Notification.id == notification_id).first()

            if not user or not notif:
                return

            subject = f"[FileMeshy] {notif.title}"

            severity_colors = {
                "error":   "#dc2626",
                "warning": "#d97706",
                "success": "#16a34a",
                "info":    "#2563eb",
            }
            color = severity_colors.get(notif.severity, "#2563eb")

            action_link = ""
            if notif.action_url:
                action_link = f"""
                <div style="margin-top: 20px;">
                    <a href="{settings.FRONTEND_URL}{notif.action_url}"
                       style="background-color: #3A64D9; color: white; padding: 10px 20px;
                              border-radius: 6px; text-decoration: none; font-weight: bold;">
                        Ver detalle
                    </a>
                </div>"""

            html_content = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;font-family:Arial,sans-serif;background:#f5f5f5;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:20px;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0"
           style="background:#ffffff;border-radius:8px;overflow:hidden;">
      <tr>
        <td style="background:linear-gradient(135deg,#3A64D9 0%,#254EC1 100%);
                   padding:30px 20px;text-align:center;">
          <h1 style="color:#ffffff;margin:0;font-size:22px;">FileMeshy</h1>
        </td>
      </tr>
      <tr>
        <td style="padding:30px;">
          <div style="border-left:4px solid {color};padding-left:16px;margin-bottom:20px;">
            <h2 style="margin:0 0 8px 0;color:#0B1638;font-size:18px;">{notif.title}</h2>
            <p style="margin:0;color:#555555;line-height:1.6;">{notif.message}</p>
          </div>
          {action_link}
        </td>
      </tr>
      <tr>
        <td style="background:#f8f9fa;padding:20px;text-align:center;
                   border-top:1px solid #e0e0e0;">
          <p style="color:#999999;margin:0;font-size:12px;">
            FileMeshy — Este es un correo automático, no respondas a este mensaje.
          </p>
        </td>
      </tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""

            text_content = f"[FileMeshy] {notif.title}\n\n{notif.message}"

            result = EmailService._send_email(
                to_email=user.email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                db=db,
            )

            if result:
                logger.info(f"Email notificación enviado a {user.email} (notif={notification_id})")
            else:
                logger.warning(f"Email notificación falló para {user.email} (notif={notification_id})")

    except Exception as exc:
        logger.error(f"send_notification_email error: {exc}")
        raise self.retry(exc=exc, countdown=120 * (self.request.retries + 1))


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120,
                 name="app.worker.tasks.email.send_welcome_email",
                 queue="emails")
def send_welcome_email(self, tenant_schema: str | None, user_id: UUID):
    """Envía email de bienvenida a un usuario recién creado."""
    try:
        with get_worker_db(schema_name=tenant_schema) as db:
            from app.users.models import User
            from app.notifications.service import EmailService

            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return

            name = f"{user.first_name} {user.last_name}".strip() or user.email
            result = EmailService.send_welcome_email(email=user.email, name=name)

            if result:
                logger.info(f"Email bienvenida enviado a {user.email}")

    except Exception as exc:
        logger.error(f"send_welcome_email error: {exc}")
        raise self.retry(exc=exc, countdown=120 * (self.request.retries + 1))
