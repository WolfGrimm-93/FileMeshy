"""Ronda 12 (E4) -- canarios del bloque FastAPI/Starlette/Pydantic.

Cubren los puntos que un salto de Starlette 0.41 -> 1.x podia romper en
silencio: arranque/apagado (lifespan), CORS en respuestas de error, cuerpo
JSON sin Content-Type, Host header raro y multipart con nombre Unicode +
campos de formulario. Van por HTTP real (fixture `client`) salvo el de
lifespan, que ejecuta el ciclo de vida de la app en proceso."""
from __future__ import annotations

import asyncio
import io
import logging

import httpx

from app.core.config import settings

from conftest import BASE_URL, auth_headers, login_user, register_user


def test_lifespan_runs_startup_and_shutdown_hooks(caplog):
    """El arranque real (verificacion de BD) y el apagado corren al entrar/salir
    del ciclo de vida de la app -- si Starlette dejara de invocar los hooks
    (ej. on_event eliminado en 1.0), este test falla."""
    from app.main import app

    async def _run():
        async with app.router.lifespan_context(app):
            pass

    with caplog.at_level(logging.INFO):
        asyncio.run(_run())
    messages = " | ".join(r.getMessage() for r in caplog.records)
    assert "Starting application" in messages
    assert "Application ready to receive requests" in messages
    assert "Shutting down application" in messages


def test_cors_headers_present_on_error_response_for_allowed_origin(client):
    origin = settings.BACKEND_CORS_ORIGINS[0]
    resp = client.get("/files", headers={"Origin": origin})  # sin token -> 401
    assert resp.status_code in (401, 403)
    assert resp.headers.get("access-control-allow-origin") == origin
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_not_reflected_for_disallowed_origin_on_error(client):
    resp = client.get("/files", headers={"Origin": "https://evil.example.org"})
    assert resp.status_code in (401, 403)
    assert "access-control-allow-origin" not in resp.headers


def test_cors_preflight_ok_for_allowed_origin(client):
    origin = settings.BACKEND_CORS_ORIGINS[0]
    resp = client.options(
        "/auth/login",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == origin


def test_json_body_with_explicit_content_type_works(client):
    creds = register_user(client)
    resp = client.post("/auth/login", json={"email": creds["email"], "password": creds["password"]})
    assert resp.status_code == 200
    client.cookies.clear()


def test_json_body_without_content_type_never_5xx(client):
    """FastAPI >= 0.132 exige Content-Type JSON estricto: sin el header el
    cuerpo ya no se parsea. Aceptable (el frontend y httpx lo mandan), pero
    tiene que ser un 4xx limpio, nunca un 500."""
    resp = client.post(
        "/auth/login",
        content=b'{"email": "x@example.com", "password": "y"}',
        headers={"Content-Type": ""},
    )
    assert 400 <= resp.status_code < 500, resp.text


def test_unusual_host_header_never_5xx():
    """Cada Host raro se envía por HTTP real. Si el servidor cierra la conexión
    o el cliente no puede armar el request (`a b`, `[::1` pueden ser rechazados
    por h11/httpx antes de salir), ese caso se cuenta como "rechazado". El test
    exige que AL MENOS UNO haya obtenido respuesta (los hosts bien formados
    `evil.example.org` y `localhost:9999` siempre la obtienen) y que NINGUNA
    respuesta sea 5xx."""
    answered = []
    for host in ("evil.example.org", "localhost:9999", "a b", "[::1"):
        try:
            resp = httpx.get(f"{BASE_URL}/health", headers={"Host": host}, timeout=10)
        except httpx.HTTPError:
            continue  # rechazado antes de responder: válido, pero no cuenta como respuesta
        assert resp.status_code < 500, (host, resp.status_code)
        answered.append(host)
    assert answered, "ningún request con Host raro llegó a obtener respuesta: el test no comprobó nada"
    assert "evil.example.org" in answered  # host bien formado: tiene que responder


def test_health_and_root_respond(client):
    assert httpx.get(f"{BASE_URL}/health", timeout=10).status_code == 200
    assert httpx.get(f"{BASE_URL}/", timeout=10).json()["status"] == "online"


def test_multipart_upload_with_unicode_name_and_form_field(client):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        data={"folder_id": ""},
        files={"file": ("canario ñ 日本.txt", io.BytesIO(b"x" * 2048), "text/plain")},
    )
    # folder_id vacio -> 201 (None) o 422 segun la version; lo que importa es que no sea 5xx
    assert resp.status_code < 500, resp.text
