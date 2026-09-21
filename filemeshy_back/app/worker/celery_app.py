"""
Instancia Celery principal — FileMeshy Worker.

Colas:
  critical   → notificaciones urgentes de seguridad (intentos de login fallidos)
  default    → notificaciones normales, seguridad
  emails     → envío de emails (con rate limiting)
  reports    → generación de snapshots y vistas materializadas
  maintenance → limpieza y mantenimiento periódico, y (Ronda 7) backups
               automáticos de Postgres/MinIO -- reusa esta cola en vez de
               una propia: son tareas de infraestructura de la misma
               naturaleza (corren de madrugada, no son sensibles a latencia)
               que ya conviven acá (cleanup-temp-files, purge-deleted-...).
  indexing   → extracción de texto/OCR de archivos (Ronda 6), cola propia
               separada de 'default' -- OCR puede tardar bastante (ver
               TASK_TIME_LIMIT_SECONDS en app/worker/tasks/indexing.py), no
               debería hacer esperar notificaciones u otras tareas rápidas
               si el worker está ocupado indexando un PDF grande.
"""

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init
from kombu import Queue
from sqlalchemy.orm import configure_mappers

from app.core.config import settings


def _register_all_orm_models() -> None:
    """Importa TODOS los modelos SQLAlchemy de la app y fuerza
    `configure_mappers()` -- centraliza acá (un solo lugar) un workaround
    que antes vivía duplicado ad-hoc en cada tarea de Celery que hace una
    query ORM directa (`purge_deleted_files_and_folders` en maintenance.py,
    y `index_file_content` en indexing.py, Ronda 6).

    Motivo: varias relaciones ORM del proyecto resuelven su target como
    STRING ('User', 'Role', 'Session', ...), no como referencia de clase
    real (ver docstrings de `app/files/models.py`/`app/tags/models.py`) --
    SQLAlchemy los busca en su registry declarativo recién la PRIMERA vez
    que se ejecuta CUALQUIER query ORM en el proceso. Si en ese momento el
    módulo que define esa clase todavía no se importó ni una sola vez,
    `configure_mappers()` revienta con `InvalidRequestError` -- y peor,
    DEJA EL REGISTRY ROTO PARA SIEMPRE en ese proceso, sin que reintentos
    posteriores lo arreglen.

    Bug real de producción (Ronda 6, revisión adversarial 2026-09-21):
    `index_file_content` sí tenía su propio import defensivo, pero
    `app.worker.tasks.email` NO -- si una tarea de email corría PRIMERO en
    el proceso del worker real y disparaba `configure_mappers()` sin que
    `Session` (de `app.auth.models`) estuviera importado todavía, el
    registry quedaba roto para TODO el proceso, y las tareas de indexación
    que corrían DESPUÉS (con su propio import ya correcto) fallaban igual
    -- el fallo de configuración ya había quedado cacheado antes de que
    `indexing.py` llegara a importar nada. Confirmado en logs reales de
    `celery_worker`: fallo reproducible y persistente, no timing.

    La solución de fondo no es que cada tarea nueva copie el mismo
    workaround a mano (era cuestión de tiempo hasta que una quinta tarea
    lo olvidara) sino garantizar que esto corra UNA sola vez, ANTES de que
    cualquier tarea se ejecute, sin importar cuál corra primero -- ver los
    dos puntos donde se invoca esta función más abajo."""
    from app.auth.models import Session, PasswordResetSession  # noqa: F401
    from app.users.models import User  # noqa: F401
    from app.access_control.models import (  # noqa: F401
        Role, Permission, RolePermission, UserPermissionOverride,
    )
    from app.tenants.models import Tenant  # noqa: F401
    from app.audit.models import AuditLog  # noqa: F401
    from app.configuration.models import (  # noqa: F401
        SystemConfiguration, UserPreferences, SecurityPolicies,
    )
    from app.notifications.models import Notification  # noqa: F401
    from app.files.models import Folder, File, Share, FileVersion, FileContentIndex  # noqa: F401
    from app.storage_quota.models import UserStorageQuota  # noqa: F401
    from app.tags.models import Tag, file_tags, folder_tags  # noqa: F401
    from app.backups.models import BackupRun  # noqa: F401

    configure_mappers()


@worker_process_init.connect
def _on_worker_process_init(**kwargs) -> None:
    """Corre UNA vez por proceso HIJO real del worker Celery (pool prefork),
    antes de que consuma su primera tarea -- es el hook correcto para esto
    según la propia documentación de Celery (setup post-fork), a diferencia
    de solo importar los modelos a nivel de módulo (que puede no alcanzar
    según el pool/modelo de concurrencia usado). Ver docstring de
    `_register_all_orm_models`."""
    _register_all_orm_models()


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
            Queue("indexing",    routing_key="indexing"),
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
            # Backups automáticos (Ronda 7) -- misma cola que mantenimiento,
            # ver comentario de "Colas" más arriba.
            "app.worker.tasks.backups.*":                             {"queue": "maintenance"},
            # Indexación de contenido/OCR (Ronda 6) -- cola propia, ver
            # comentario de "Colas" más arriba.
            "app.worker.tasks.indexing.*":                            {"queue": "indexing"},
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
            # Backup completo de Postgres (Ronda 7) — 2 AM diario, ANTES de
            # las tareas de limpieza (3-4 AM): un backup no debería competir
            # por recursos/turno con la purga de papelera ni la limpieza de
            # temporales del mismo worker. Verificación real en
            # `GET /admin/backups` (app/backups/router.py) -- no es "correr
            # un cron y esperar que funcione", ver docstring del módulo de
            # la tarea.
            "backup-postgres-daily": {
                "task": "app.worker.tasks.backups.backup_postgres",
                "schedule": crontab(hour=2, minute=0),
                "options": {"queue": "maintenance"},
            },
            # Backup de objetos de MinIO a destino S3 externo (Ronda 7,
            # condicional) — 2:15 AM diario, staggered del de Postgres de
            # arriba. Si no hay destino externo configurado
            # (settings.BACKUP_S3_*), la tarea se registra como 'failed' con
            # el motivo y no hace nada más -- ver
            # app/worker/tasks/backups.py::backup_minio_objects.
            "backup-minio-daily": {
                "task": "app.worker.tasks.backups.backup_minio_objects",
                "schedule": crontab(hour=2, minute=15),
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
        "app.worker.tasks.indexing",
        "app.worker.tasks.backups",
    ])

    return app


celery_app = create_celery_app()

# Además de la señal `worker_process_init` (que solo dispara DENTRO de un
# proceso worker de Celery real, ver más arriba), se llama también acá,
# a nivel de módulo -- para cubrir los otros dos procesos que ejecutan
# tareas de este mismo código SIN pasar por un worker real:
#   1. El proceso del backend/API (uvicorn), que importa
#      `app.worker.tasks.*` de forma diferida solo para encolar con
#      `.delay()` (ver `_enqueue_content_indexing` en app/files/router.py)
#      -- nunca emite `worker_process_init`, pero cualquier import de
#      `app.worker.celery_app` (transitivo, vía `from app.worker.celery_app
#      import celery_app` al inicio de cada módulo de app/worker/tasks/)
#      ya deja los mappers configurados antes de que ese proceso haga
#      ninguna query ORM propia.
#   2. Tests que invocan una tarea DIRECTO como función Python normal, sin
#      pasar por el broker ni por un worker real (ver
#      `tests/test_content_indexing.py`/`tests/test_purge_file_versions_quota.py`)
#      -- ese proceso de pytest tampoco emite `worker_process_init`.
_register_all_orm_models()
