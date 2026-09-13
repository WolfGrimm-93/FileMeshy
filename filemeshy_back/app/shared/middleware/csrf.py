"""Middleware CSRF (patrón doble-submit cookie).

Defensa en profundidad además de `SameSite=lax` en `refresh_token` (que ya
cubre el riesgo principal): si algún día `SameSite` se relaja para un flujo
nuevo, o un navegador/subdominio no lo respeta como se espera, esto sigue
bloqueando la mutación.

ASGI puro (no `BaseHTTPMiddleware`), mismo motivo que TenantMiddleware/
UTF8Middleware en app/main.py: no serializar requests concurrentes.

Cómo funciona: al loguearse (o refrescar), el backend deja una cookie
`filemeshy_csrf_token` (ver CSRF_COOKIE_NAME) NO httponly (el frontend la
lee por JS y la reenvía como header `X-XSRF-TOKEN` en cada request que muta
estado -- ver
filemeshy_front/src/shared/config/axios.ts). Un atacante cross-site puede lograr
que el navegador de la víctima mande la cookie sola, pero no puede LEER esa
cookie (same-origin policy) para poner el header que hace falta -- por eso
alcanza con comparar que cookie y header coincidan, sin guardar nada
server-side.
"""
import logging
import secrets

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

logger = logging.getLogger("filemeshy.csrf")

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# Rutas exentas: sin sesión todavía (login/register), el propio refresh/logout
# (protegidos por el httpOnly + rotación de JTI, no por este mecanismo), el
# flujo de password-reset (cookies propias, SameSite=strict, scope de path
# separado) y la API de plataforma (otro modelo de auth por API key, sin
# cookies de navegador).
EXEMPT_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/static/",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",
    "/api/v1/auth/2fa/verify-login",
    "/api/v1/auth/password-reset",
    "/api/v1/platform",
)


def _cookie_valor(cookie_header: str, nombre: str) -> str | None:
    for parte in cookie_header.split(";"):
        if "=" not in parte:
            continue
        clave, _, valor = parte.strip().partition("=")
        if clave == nombre:
            return valor
    return None


class CSRFMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        path = scope.get("path", "")

        if method in SAFE_METHODS or any(path.startswith(p) for p in EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        cookie_header = headers.get(b"cookie", b"").decode("latin-1")
        cookie_token = _cookie_valor(cookie_header, CSRF_COOKIE_NAME)

        if not cookie_token:
            # Sin sesión iniciada todavía (nunca hizo login) -- nada que
            # proteger acá, el 401 de auth se encarga después.
            await self.app(scope, receive, send)
            return

        header_token = headers.get(CSRF_HEADER_NAME.encode("latin-1"), b"").decode("latin-1")

        if not header_token or not secrets.compare_digest(header_token, cookie_token):
            logger.warning(f"[CSRF] Token ausente o no coincide en {method} {path}")
            response = JSONResponse(status_code=403, content={"detail": "Token CSRF inválido o ausente"})
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
