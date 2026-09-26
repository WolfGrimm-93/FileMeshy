from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Receive, Scope, Send
from app.shared.utils.datetime_iso import to_utc_iso
from app.core.config import settings
from app.core.database import check_database_connection
from app.audit.service import AuditMiddleware
from app.shared.middleware.tenant import TenantMiddleware
from app.shared.middleware.csrf import CSRFMiddleware
from app.api.v1.router import api_router
from app.api.v1.exception_handlers import register_exception_handlers
from app.auth.service import get_current_active_user
from app.users.models import User
import os
import logging
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ===== TRAILING SLASH MIDDLEWARE (ASGI puro) =====
class TrailingSlashMiddleware:
    """
    Añade slash solo a las rutas de colección que lo requieren.
    Calculado dinámicamente al primer request para no romper rutas de auth u otras.
    """
    def __init__(self, app: ASGIApp, fastapi_app) -> None:
        self.app = app
        self._fastapi_app = fastapi_app
        self._needs_slash: set | None = None

    def _build_set(self) -> set:
        write_methods = {"POST", "PUT", "PATCH", "DELETE"}
        with_slash: set = set()
        without_slash: set = set()
        for r in self._fastapi_app.routes:
            if not hasattr(r, "methods") or not r.methods:
                continue
            if not any(m in r.methods for m in write_methods):
                continue
            if "{" in r.path:
                continue
            if r.path.endswith("/"):
                with_slash.add(r.path.rstrip("/") or "/")
            else:
                without_slash.add(r.path)
        # Solo agregar slash a paths que NO tienen versión sin slash
        return with_slash - without_slash

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            if self._needs_slash is None:
                self._needs_slash = self._build_set()
            path: str = scope.get("path", "")
            if path in self._needs_slash:
                new_path = path + "/"
                scope = {**scope, "path": new_path, "raw_path": new_path.encode()}
        await self.app(scope, receive, send)


# ===== UTF-8 CHARSET MIDDLEWARE (ASGI puro - no serializa requests) =====
class UTF8Middleware:
    """
    Middleware ASGI puro para forzar charset UTF-8 en respuestas JSON.
    A diferencia de BaseHTTPMiddleware, NO serializa requests concurrentes.
    """
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                ct = headers.get(b"content-type", b"").decode()
                if ct.startswith("application/json") and "charset" not in ct:
                    new_headers = [
                        (k, v) if k != b"content-type" else (k, b"application/json; charset=utf-8")
                        for k, v in message.get("headers", [])
                    ]
                    message = {**message, "headers": new_headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)

# ===== SECURITY HEADERS MIDDLEWARE (ASGI puro) =====
class SecurityHeadersMiddleware:
    """
    Middleware ASGI puro (mismo patrón que UTF8Middleware) que agrega headers
    de seguridad HTTP estándar a toda respuesta. HSTS solo en producción --
    en dev/local casi siempre se sirve por HTTP, y HSTS fuerza HTTPS en el
    navegador durante meses, rompiendo el acceso por http://localhost.
    """
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"content-security-policy", b"default-src 'self'; frame-ancestors 'none'"),
                ])
                if settings.ENVIRONMENT == "production":
                    headers.append(
                        (b"strict-transport-security", b"max-age=63072000; includeSubDomains")
                    )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)


# ===== LIFESPAN (arranque y cierre) =====
# Ronda 12: reemplaza los `@app.on_event("startup"/"shutdown")` (deprecados y
# eliminados en Starlette 1.0). Cubierto por
# tests/test_app_canaries.py::test_lifespan_runs_startup_and_shutdown_hooks.
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Arranque: verificar conexión a BD. El esquema lo aplica Alembic
    (alembic upgrade head corre antes que este proceso, ver Dockerfile/docker-compose.yml).
    Cierre: limpiar recursos."""
    logger.info("[APP] Starting application...")

    if check_database_connection(max_retries=5, retry_interval=2):
        logger.info("[APP] Application ready to receive requests")
    else:
        logger.warning(
            "[APP] Application started WITHOUT database connection.\n"
            "   API requests will fail until database is available."
        )

    yield

    logger.info("[APP] Shutting down application...")


# ===== APP INSTANCE =====
# En producción, deshabilitar documentación pública
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API para FileMeshy - Almacenamiento de archivos",
    version=settings.PROJECT_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    redirect_slashes=False,
    lifespan=lifespan,
)

# ===== TRAILING SLASH MIDDLEWARE =====
app.add_middleware(TrailingSlashMiddleware, fastapi_app=app)

# ===== UTF-8 MIDDLEWARE (ASGI puro) =====
# Forzar charset UTF-8 en respuestas JSON. Usa ASGI puro para no serializar requests concurrentes.
app.add_middleware(UTF8Middleware)

# ===== SECURITY HEADERS MIDDLEWARE (ASGI puro) =====
# CSP/X-Frame-Options/X-Content-Type-Options/Referrer-Policy siempre; HSTS solo en producción.
app.add_middleware(SecurityHeadersMiddleware)

# ===== AUDIT MIDDLEWARE =====
# Registra automáticamente todas las operaciones POST/PUT/PATCH/DELETE en audit_log.
app.add_middleware(AuditMiddleware)

# ===== CSRF MIDDLEWARE (doble-submit cookie) =====
# Defensa en profundidad ademas de SameSite=lax en refresh_token -- siempre
# activo (local y cloud), no es especifico de multi-tenancy.
app.add_middleware(CSRFMiddleware)

# ===== TENANT MIDDLEWARE (solo en modo cloud) =====
# Registro condicional: en modo local el middleware ni se instancia (cero overhead).
if settings.DEPLOYMENT_MODE == "cloud":
    app.add_middleware(TenantMiddleware)

# ===== CORS MIDDLEWARE - DEBE IR ANTES DE LAS RUTAS =====
# Fuente de verdad: BACKEND_CORS_ORIGINS en config.py / .env
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],  # OPTIONS requerido para preflight CORS
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-Tenant-Slug", "X-Xsrf-Token", "X-Client-Type", "X-Session-Slot"],  # Headers esenciales (X-Tenant-Slug: fase 2 multi-tenancy; X-Xsrf-Token: CSRF doble-submit; X-Client-Type: refresh token en body para desktop, ver auth.service.ts; X-Session-Slot: cambio de usuario temporal, ver axios.ts/auth.service.ts)
    expose_headers=["Content-Type", "Authorization"],  # Solo exponer los necesarios
    max_age=3600,  # Cache preflight por 1 hora
)

# ===== STATIC FILES =====
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

# ===== FAVICON =====
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve favicon."""
    favicon_path = os.path.join(static_path, "favicon.svg")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    return JSONResponse(status_code=404, content={"detail": "Favicon not found"})


# ===== ROUTES =====
app.include_router(api_router)

# ===== PLATFORM ROUTER (Fase 3 -- solo en modo cloud) =====
# Registro condicional, mismo patrón que TenantMiddleware: en modo local ni
# siquiera existe la tabla `tenants` con más de una fila que administrar.
if settings.DEPLOYMENT_MODE == "cloud":
    from app.platform.router import platform_router
    app.include_router(platform_router, prefix=settings.API_V1_PREFIX)

# ===== REGISTER EXCEPTION HANDLERS =====
register_exception_handlers(app)


# ===== ERROR HANDLERS - Asegurar que CORS headers siempre estén presentes =====
def _cors_headers_for(request) -> dict:
    """Arma los headers CORS solo si el Origin del request está en el
    allowlist (mismo criterio que CORSMiddleware, ver BACKEND_CORS_ORIGINS) --
    NUNCA reflejar el Origin recibido sin validar: con
    Allow-Credentials=true eso permite a cualquier sitio leer la respuesta
    de un usuario autenticado (CSRF/robo de datos cross-origin)."""
    origin = request.headers.get("origin")
    if origin and origin in settings.BACKEND_CORS_ORIGINS:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        }
    return {}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    """Manejar excepciones HTTP con CORS headers.

    Ronda 10 -- bug encontrado: esto reconstruía la respuesta pasando SOLO
    `_cors_headers_for(request)` como `headers`, descartando por completo
    `exc.headers` -- cualquier endpoint que levante `HTTPException(...,
    headers=...)` perdía esos headers en el camino (hoy al menos el 503 de
    admisión de subidas grandes con `Retry-After`, ver
    app/uploads/service.py::_try_reserve_admission_slot). Fusionamos ambos
    dicts -- `_cors_headers_for(request)` último a propósito, así sus claves
    (`Access-Control-*`) SIEMPRE ganan si algún día `exc.headers` trajera
    por error una clave con ese mismo nombre (no debería pasar hoy, ninguna
    HTTPException del código pone headers CORS a mano, pero así ninguna
    HTTPException futura puede pisar el CORS validado de este handler).

    OJO -- hallazgo importante de esta misma ronda, verificando el fix en
    vivo: ESTE handler está registrado para `StarletteHTTPException` (la
    clase PADRE), pero TODO el código de la app levanta
    `fastapi.HTTPException` (la subclase, `from fastapi import
    HTTPException`) -- y FastAPI/Starlette despachan por el tipo MÁS
    ESPECÍFICO del MRO de la excepción real, no por orden de registro. Como
    `app/api/v1/exception_handlers.py::register_exception_handlers` registra
    un handler aparte específicamente para `fastapi.HTTPException`, ESE es
    el que gana siempre en la práctica para cualquier `HTTPException` real
    del código -- confirmado en vivo imprimiendo
    `app.exception_handlers.keys()` (ambas clases quedan como entradas
    separadas) y reproduciendo el bug de Retry-After contra el endpoint real
    ANTES de arreglar TAMBIÉN `typed_exception_handler` en ese otro archivo
    (el fix de acá solo, sin ese otro, no alcanzaba -- el 503 seguía sin el
    header). Este handler de acá queda como defensa para el caso de que algo
    levante un `starlette.exceptions.HTTPException` puro alguna vez (hoy no
    pasa en este código), pero el fix que realmente importa para el bug
    reportado está en `app/api/v1/exception_handlers.py::typed_exception_handler`."""
    headers = {**(exc.headers or {}), **_cors_headers_for(request)}
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Manejar excepciones generales con CORS headers."""
    import logging
    logger = logging.getLogger("app")
    logger.exception(f"Unhandled error on {request.method} {request.url.path}")

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Error interno del servidor",
        },
        headers=_cors_headers_for(request),
    )


@app.get("/", tags=["root"])
async def read_root():
    """Endpoint raíz - Información básica de la API."""
    return {
        "message": "FileMeshy API",
        "version": settings.PROJECT_VERSION,
        "status": "online"
    }


@app.get("/health", tags=["health"])
async def health_check():
    """Health check público - Solo indica si la API está viva.
    
    Para monitoreo externo (load balancers, uptime monitors).
    No requiere autenticación para facilitar monitoreo.
    """
    import asyncio
    
    # Verificar BD de forma async con timeout
    db_status = "disconnected"
    try:
        # Ejecutar la consulta en un thread pool para no bloquear
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, lambda: _check_db_sync()),
            timeout=5.0  # Timeout de 5 segundos
        )
        db_status = "connected"
    except asyncio.TimeoutError:
        logger.error("Health check - DB timeout")
    except Exception as e:
        logger.error(f"Health check - DB error: {str(e)}")
    
    # En producción, solo retornar status simple
    if not settings.DEBUG:
        return {
            "status": "healthy" if db_status == "connected" else "unhealthy"
        }
    
    # En desarrollo, mostrar más detalles
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "environment": "development"
    }


def _check_db_sync():
    """Helper síncrono para verificar la conexión a la BD."""
    from app.core.database import engine
    from sqlalchemy import text
    
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        return True


@app.get("/health/detailed", tags=["health"])
async def health_check_detailed(
    current_user: User = Depends(get_current_active_user)
):
    """Health check detallado - Solo para usuarios autenticados (ADMIN/SUPER_ADMIN).

    Ronda 10 -- el payload anterior exponía de más para lo que es un
    healthcheck real (hallazgo de la auditoría, ver pendiente.md): versión
    completa de Postgres (`SELECT version()`, con el build string entero del
    binario), `sys.version`/`platform.python_version()`/`platform.platform()`
    (versión de Python y del OS del contenedor) y el flag `settings.DEBUG`.
    Nada de eso es necesario para responder "¿está la app sana?" -- son
    detalles de la pila interna que un endpoint autenticado no debería
    seguir regalando de más (defensa en profundidad: aunque ya está bien
    gateado a rol admin, un token robado o un admin malicioso no necesita
    el fingerprint completo del stack para nada operativo). Criterio de
    "esencial" que se dejó: si la DB responde sí/no (para diagnosticar un
    problema real de conectividad) y qué versión de la APP corre (para
    confirmar que un deploy se aplicó) -- nada de la versión de Python/
    Postgres/OS ni el flag de debug.
    """
    from app.core.database import engine
    from sqlalchemy import text
    from datetime import datetime

    # Verificar que el usuario tenga permisos de admin
    if not current_user.role_obj or current_user.role_obj.name not in ["SUPER_ADMIN", "ADMIN"]:
        raise HTTPException(
            status_code=403,
            detail="No tienes permisos para acceder a esta información"
        )

    # Verificar BD -- solo conectividad, sin exponer el version string completo.
    db_status = "disconnected"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_status = "connected"
    except Exception:
        pass

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "timestamp": to_utc_iso(datetime.utcnow()),
        "database": {
            "status": db_status,
        },
        "application": {
            "name": settings.PROJECT_NAME,
            "version": settings.PROJECT_VERSION,
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )

