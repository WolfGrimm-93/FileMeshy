"""
Sesión de base de datos para tareas Celery.

Las tareas corren fuera del ciclo de vida de FastAPI,
por lo que no pueden usar la dependencia `get_db` del API.
"""

from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, tenant_schema_ctx


@contextmanager
def get_worker_db(schema_name: Optional[str] = None) -> Generator[Session, None, None]:
    """Context manager para obtener una sesión DB en tareas Celery.

    Si se pasa `schema_name`, fija `tenant_schema_ctx` (mismo patrón que
    TenantMiddleware y tenant_provisioning.sembrar_cliente_nuevo) para que
    el listener de "checkout" del pool (app/core/database.py) apunte el
    search_path al schema de ese tenant. Sin schema_name, usa lo que ya
    esté seteado en el ContextVar -- en modo local, o si nunca se fijó
    nada, cae en el comportamiento de siempre (public).
    """
    token = None
    if schema_name is not None:
        token = tenant_schema_ctx.set(schema_name)
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        if token is not None:
            tenant_schema_ctx.reset(token)


def listar_tenant_schemas_activos() -> list[str]:
    """Schemas de todos los tenants activos (tabla `tenants`, vive en public).
    Solo tiene sentido en modo cloud -- en local devuelve lista vacía."""
    if settings.DEPLOYMENT_MODE != "cloud":
        return []
    from sqlalchemy import text

    db = SessionLocal()
    try:
        rows = db.execute(text("SELECT schema_name FROM public.tenants WHERE is_active = true")).all()
        return [r[0] for r in rows]
    finally:
        db.close()


def iter_tenant_schemas() -> Generator[Optional[str], None, None]:
    """Itera los schemas a procesar en una tarea periódica.

    Cloud: un yield por tenant activo (puede no yieldar nada si no hay ninguno).
    Local: un único yield con None -- get_worker_db(schema_name=None) no toca
    tenant_schema_ctx, comportamiento actual intacto.
    """
    if settings.DEPLOYMENT_MODE != "cloud":
        yield None
        return
    for schema in listar_tenant_schemas_activos():
        yield schema
