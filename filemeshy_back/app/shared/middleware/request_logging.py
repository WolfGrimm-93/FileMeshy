"""
Middleware para logging detallado de requests con timestamp y duración

NOTA (migración a monolito modular, Implementador 2): confirmado con grep
exhaustivo sobre app/main.py que `RequestLoggingMiddleware` NUNCA se registra
vía `app.add_middleware(...)` -- es código muerto hoy, ya documentado así en
RECON_RIESGOS.md. Se migra tal cual (sin activarlo ni borrarlo, decisión de
producto fuera de este alcance) -- no agregarlo a main.py sin que alguien lo
pida explícitamente.
"""
import time
import logging
from datetime import datetime
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware que registra todas las peticiones HTTP con:
    - Timestamp (fecha y hora)
    - Formato similar a Uvicorn default
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Capturar hora de inicio
        start_time = time.time()
        start_datetime = datetime.utcnow()

        # Ejecutar la petición
        response = await call_next(request)

        # Calcular duración
        duration_ms = (time.time() - start_time) * 1000

        # Formatear timestamp
        timestamp = start_datetime.strftime("%Y-%m-%d %H:%M:%S")

        # Extraer información
        method = request.method
        path = request.url.path
        query = request.url.query
        client_ip = request.client.host if request.client else "unknown"
        client_port = request.client.port if request.client else "unknown"
        status_code = response.status_code

        # Construir la línea de log similar a Uvicorn
        full_path = path
        if query:
            full_path += f"?{query}"

        # Log con el formato original de Uvicorn pero con fecha
        logger.info(
            f"[{timestamp}] {client_ip}:{client_port} - \"{method} {full_path} HTTP/1.1\" {status_code} OK ({duration_ms:.0f}ms)"
        )

        return response
