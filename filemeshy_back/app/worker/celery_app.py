"""
Instancia Celery principal — FileMeshy Worker.

Colas:
  critical   → notificaciones urgentes de seguridad (intentos de login fallidos)
  default    → notificaciones normales, seguridad
  emails     → envío de emails (con rate limiting)
  reports    → generación de snapshots y vistas materializadas
  maintenance → limpieza y mantenimiento periódico
"""

from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from app.core.config import settings


def create_celery_app() -> Celery:
    app = Celery("filemeshy_worker")

    app.conf.update(
        # ─── Broker y backend ───────────────────────────────────────────────
        broker_url=settings.CELERY_BROKER_URL,
        result_backend=settings.CELERY_RESULT_BACKEND,

        # ─── Serialización ──────────────────────────────────────────────────
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="America/Santo_Domingo",
        enable_utc=True,

        # ─── Colas ──────────────────────────────────────────────────────────
        task_queues=(
            Queue("critical",    routing_key="critical"),
            Queue("default",     routing_key="default"),
            Queue("emails",      routing_key="emails"),
            Queue("reports",     routing_key="reports"),
            Queue("maintenance", routing_key="maintenance"),
        ),
        task_default_queue="default",
        task_default_routing_key="default",

        # ─── Routing por tarea ──────────────────────────────────────────────
        task_routes={
            # Email (rate limited)
            "app.worker.tasks.email.*":                               {"queue": "emails"},
            # Mantenimiento
            "app.worker.tasks.maintenance.*":                         {"queue": "maintenance"},
            "app.worker.tasks.security.*":                            {"queue": "maintenance"},
        },

        # ─── Reintentos ─────────────────────────────────────────────────────
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_max_retries=3,

        # ─── Resultados ─────────────────────────────────────────────────────
        result_expires=3600,  # 1 hora

        # ─── Eventos (necesario para Flower) ────────────────────────────────
        worker_send_task_events=True,
        task_send_sent_event=True,

        # ─── Conexión broker ────────────────────────────────────────────────
        broker_connection_retry_on_startup=True,

        # ─── Beat schedule (tareas periódicas) ──────────────────────────────
        beat_schedule={
            # Sesiones expiradas — cada 6 horas
            "cleanup-expired-sessions": {
                "task": "app.worker.tasks.maintenance.cleanup_expired_sessions",
                "schedule": crontab(minute=0, hour="*/6"),
                "options": {"queue": "maintenance"},
            },
            # Notificaciones leídas antiguas — domingos 3 AM
            "cleanup-old-notifications": {
                "task": "app.worker.tasks.maintenance.cleanup_old_notifications",
                "schedule": crontab(hour=3, minute=0, day_of_week=0),
                "options": {"queue": "maintenance"},
            },
            # Audit logs antiguos — primer domingo del mes 4 AM
            "cleanup-old-audit-logs": {
                "task": "app.worker.tasks.maintenance.cleanup_old_audit_logs",
                "schedule": crontab(hour=4, minute=0, day_of_week=0, day_of_month="1-7"),
                "options": {"queue": "maintenance"},
            },
            # Sesiones inactivas — domingos 3:30 AM
            "revoke-inactive-sessions": {
                "task": "app.worker.tasks.maintenance.revoke_inactive_sessions",
                "schedule": crontab(hour=3, minute=30, day_of_week=0),
                "options": {"queue": "maintenance"},
            },
            # Actividad sospechosa — cada hora
            "audit-suspicious-activity": {
                "task": "app.worker.tasks.security.audit_suspicious_activity",
                "schedule": crontab(minute=5),  # :05 de cada hora
                "options": {"queue": "maintenance"},
            },
            # Limpieza archivos temporales MinIO — 3 AM diario
            "cleanup-temp-files": {
                "task": "app.worker.tasks.maintenance.cleanup_temp_files",
                "schedule": crontab(hour=3, minute=0),
                "options": {"queue": "maintenance"},
            },
            # Purga definitiva de papelera (archivos/carpetas, >30 días) — 4 AM diario,
            # staggered de cleanup-temp-files (3 AM).
            "purge-deleted-files-and-folders": {
                "task": "app.worker.tasks.maintenance.purge_deleted_files_and_folders",
                "schedule": crontab(hour=4, minute=0),
                "options": {"queue": "maintenance"},
            },
        },
    )

    # Autodiscover tasks en app/worker/tasks/
    app.autodiscover_tasks([
        "app.worker.tasks.email",
        "app.worker.tasks.maintenance",
        "app.worker.tasks.security",
    ])

    return app


celery_app = create_celery_app()
