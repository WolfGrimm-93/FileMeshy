"""Middleware de resolución de tenant (modo DEPLOYMENT_MODE=cloud).

ASGI puro (no BaseHTTPMiddleware) por el mismo motivo que TrailingSlashMiddleware
y UTF8Middleware en app/main.py: BaseHTTPMiddleware serializa requests concurrentes,
y acá conviven requests de tenants distintos en el mismo proceso.

Solo se registra en app.main cuando DEPLOYMENT_MODE == "cloud" -- en modo local
esta clase ni siquiera se instancia, cero overhead por request.
"""
import logging
import re

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.database import tenant_schema_ctx

logger = logging.getLogger("filemeshy.tenant")

# Prefijos de rutas que NO requieren tenant resuelto (mismo patrón que audit.service.SKIP_PREFIXES)
SKIP_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/static/",
    # Fase 3: administra la tabla `tenants` en sí (vive en public) -- no
    # pertenece a ningún tenant, no lleva X-Tenant-Slug. Auth propia (ver
    # get_platform_admin en app/platform/router.py), no la del login de tenant.
    "/api/v1/platform",
)

SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")

# tenant_schema_ctx vive en app.core.database porque el listener de "checkout" del pool
# (que fija el search_path de la conexión) también necesita leerlo -- misma instancia de
# ContextVar, nunca una variable global de módulo (ver app/shared/utils/tenant.py, _cached_code:
# ese patrón se pisa entre requests concurrentes de tenants distintos).


def _json_error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


class TenantMiddleware:
    """Resuelve el tenant desde el header X-Tenant-Slug y guarda su schema_name en un ContextVar."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if any(path.startswith(prefix) for prefix in SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        raw_slug = headers.get(b"x-tenant-slug")

        if not raw_slug:
            response = _json_error(400, "Header X-Tenant-Slug requerido")
            await response(scope, receive, send)
            return

        slug = raw_slug.decode("latin-1")
        if not SLUG_RE.match(slug):
            response = _json_error(400, "Formato de X-Tenant-Slug inválido")
            await response(scope, receive, send)
            return

        schema_name = await self._resolve_schema(slug)
        if schema_name is None:
            response = _json_error(404, "Tenant no encontrado")
            await response(scope, receive, send)
            return
        if schema_name is False:
            response = _json_error(403, "Tenant inactivo")
            await response(scope, receive, send)
            return

        token = tenant_schema_ctx.set(schema_name)
        try:
            await self.app(scope, receive, send)
        finally:
            tenant_schema_ctx.reset(token)

    @staticmethod
    async def _resolve_schema(slug: str):
        """Busca el tenant por slug. Retorna schema_name, None (no existe) o False (inactivo)."""
        from sqlalchemy import text
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            row = db.execute(
                text("SELECT id, schema_name, is_active FROM tenants WHERE slug = :slug"),
                {"slug": slug},
            ).first()
        finally:
            db.close()

        if row is None:
            return None
        if not row.is_active:
            return False
        return row.schema_name
