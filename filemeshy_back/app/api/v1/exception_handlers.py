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

        Ronda 10 -- bug encontrado (no el que se buscaba originalmente, ver
        app/main.py::http_exception_handler para el contexto completo del
        hallazgo): ESTE es el handler que en la práctica atiende TODAS las
        `HTTPException` de la app (`fastapi.HTTPException`, lo que se usa en
        cada `raise HTTPException(...)` del código) -- no
        `app/main.py::http_exception_handler`, registrado para
        `starlette.exceptions.HTTPException` (la clase PADRE). Starlette
        despacha por el tipo MÁS ESPECÍFICO presente en el MRO de la
        excepción realmente lanzada, no por orden de registro -- confirmado
        en vivo imprimiendo `app.exception_handlers.keys()`: ambas clases
        quedan registradas por separado, y para una `fastapi.HTTPException`
        real (el 99% de los casos en este código) SIEMPRE gana el handler de
        acá, sin importar que el de `main.py` se haya registrado después.
        Por eso los 3 `return JSONResponse(...)` de abajo necesitaban el
        mismo fix que se le hizo a `main.py::http_exception_handler`:
        ninguno pasaba `headers=exc.headers`, así que CUALQUIER
        `HTTPException(..., headers=...)` (hoy, el 503 de admisión de
        subidas grandes con `Retry-After`, ver
        app/uploads/service.py::_try_reserve_admission_slot) perdía esos
        headers en el camino -- reproducido en vivo con curl directo contra
        el backend real ANTES de este fix (503 sin `Retry-After`) y
        confirmado después (503 con `Retry-After: 30` presente).

        Los headers CORS (`Access-Control-*`) NO se arman a mano acá a
        propósito -- a diferencia de `main.py::http_exception_handler`, que
        sí llama a `_cors_headers_for()`, `CORSMiddleware` (registrado como
        middleware ASGI en app/main.py) ya los agrega a CUALQUIER respuesta
        con un `Origin` válido, sin importar qué exception handler la
        generó -- confirmado en vivo: un 503 de acá con `Origin` presente
        ya traía `access-control-allow-origin` ANTES de este fix, pese a
        que este handler nunca los seteaba explícitamente.
        """

        # Caso general: cualquier ruta que ya arma su propio detail estructurado
        # {"code": ..., "message": ..., ...} -- ej. app/schemas/sale_errors.py.
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            code = exc.detail["code"]
            message = exc.detail.get("message", "Error desconocido")
            return JSONResponse(
                status_code=exc.status_code,
                content={"status": code, "message": message, "data": exc.detail},
                headers=exc.headers,
            )

        # Caso legacy: rutas de password-reset, donde detail es el código como string
        # plano y el mensaje se resuelve contra ERROR_MESSAGES.
        if "/password-reset" in request.url.path:
            error_code = exc.detail
            if isinstance(error_code, str) and error_code in ERROR_MESSAGES:
                message = ERROR_MESSAGES[error_code]
            else:
                # Ronda 12c: un detail que no es un código conocido (p. ej. el texto libre
                # del limitador de /password-reset/*: "Demasiadas solicitudes. Intenta en
                # N segundos") llegaba al usuario como "<texto>: Error desconocido". Se
                # devuelve tal cual como mensaje; el `status`/`code` queda legible y estable.
                message = str(exc.detail)
                error_code = "rate_limited" if exc.status_code == 429 else "error"
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "status": error_code,
                    "message": message,
                    "data": {"code": error_code, "message": message},
                },
                headers=exc.headers,
            )

        # Resto de rutas: comportamiento original de FastAPI, sin estructurar.
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )
