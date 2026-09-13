"""
Exception handlers globales para errores tipados.

Convierte HTTPException con códigos de error en respuestas JSON estructuradas que el
frontend puede distinguir sin parsear el texto del mensaje. Empezó siendo específico de
password-reset; REGLA-DESC lo generalizó para que cualquier ruta pueda levantar
`HTTPException(detail={"code": ..., "message": ..., ...})` y recibir el mismo formato,
sin tener que registrar un segundo exception_handler(HTTPException) -- FastAPI solo
permite uno por tipo de excepción, el último registrado pisa al anterior.
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from app.auth.schemas import (
    ERROR_MESSAGES,
)


def register_exception_handlers(app: FastAPI):
    """Registra el exception handler único de errores tipados (HTTPException)."""

    @app.exception_handler(HTTPException)
    async def typed_exception_handler(request: Request, exc: HTTPException):
        """
        Retorna, en todos los casos reconocidos:
        {
          "status": "error_code",  // Código del error (ej: "token_expired")
          "message": "Mensaje para usuario",
          "data": {
            "code": "error_code",
            "message": "Mensaje para usuario",
            ...  // campos extra del detail estructurado (ej: "threshold")
          }
        }
        """

        # Caso general: cualquier ruta que ya arma su propio detail estructurado
        # {"code": ..., "message": ..., ...} -- ej. app/schemas/sale_errors.py.
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            code = exc.detail["code"]
            message = exc.detail.get("message", "Error desconocido")
            return JSONResponse(
                status_code=exc.status_code,
                content={"status": code, "message": message, "data": exc.detail},
            )

        # Caso legacy: rutas de password-reset, donde detail es el código como string
        # plano y el mensaje se resuelve contra ERROR_MESSAGES.
        if "/password-reset" in request.url.path:
            error_code = exc.detail
            message = ERROR_MESSAGES.get(error_code, "Error desconocido")
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "status": error_code,
                    "message": message,
                    "data": {"code": error_code, "message": message},
                },
            )

        # Resto de rutas: comportamiento original de FastAPI, sin estructurar.
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
