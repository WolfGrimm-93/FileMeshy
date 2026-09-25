"""Ronda 10 -- regresión del bug de `Retry-After` descartado en el 503 de
admisión de subidas grandes (ver app/main.py::http_exception_handler).

Bug: `http_exception_handler` reconstruía la respuesta de CUALQUIER
`HTTPException` pasando SOLO `_cors_headers_for(request)` como `headers`,
descartando por completo `exc.headers` -- el único lugar de la app que hoy
levanta una `HTTPException` con headers propios es el 503 de admisión de
`/uploads/initiate` (`Retry-After: 30`, ver
app/uploads/service.py::_try_reserve_admission_slot), así que ese header
nunca llegaba al cliente real.

A diferencia de `test_large_upload_multipart.py::
test_per_user_admission_cap_isolated_from_other_users` (que llama a
`initiate_upload()` DIRECTO, sin pasar por HTTP -- nunca ejercita
`http_exception_handler`), este test va por HTTP real (fixture `client`)
para confirmar que el header efectivamente llega al cliente, que es
justamente lo que el bug rompía."""
from __future__ import annotations

import pytest

from app.core.config import settings

from conftest import auth_headers, login_user, register_user

# Tamaño por sesión: por encima de MAX_UPLOAD_SIZE_MB (100MB, fuerza el
# camino de subida grande) y muy por debajo de MAX_LARGE_UPLOAD_SIZE_MB
# (20480MB) -- no importa completarlas, solo abrirlas para llenar el cupo
# por-usuario (MAX_CONCURRENT_LARGE_UPLOADS_PER_USER=3 por defecto).
_SESSION_SIZE_BYTES = 200 * 1024 * 1024


def _initiate(client, token, name, extra_headers=None):
    """POST /uploads/initiate real -- devuelve la respuesta cruda. `/uploads/
    initiate` responde 201 (no 200) cuando abre la sesión -- confirmado en
    vivo contra el stack real."""
    return client.post(
        "/uploads/initiate",
        json={"file_name": name, "size_bytes": _SESSION_SIZE_BYTES, "mime_type": "application/octet-stream"},
        headers={**auth_headers(token), **(extra_headers or {})},
    )


def _session_id_or_none(resp) -> str | None:
    """Extrae `upload_session_id` de una respuesta 201 sin arriesgar tirar
    una excepción NUEVA -- si esto rompiera (ej. el shape de la respuesta
    cambia), el session_id real igual quedaría abierto en el servidor pero
    SIN registrar para abort, filtrando el cupo de admisión hacia otros
    tests de la suite (ver docstring de `_abort_all`, ya reproducido en vivo
    una vez armando este archivo: un `KeyError` acá adentro del `.append()`
    dejaba 8 sesiones reales colgadas). `/uploads/initiate` devuelve el
    schema `UploadInitiateResponse` directo, sin envoltorio `{"data": ...}`
    (a diferencia de `/auth/login`) -- confirmado en vivo con curl."""
    try:
        return resp.json().get("upload_session_id")
    except Exception:
        return None


@pytest.fixture
def _abort_all(client):
    """Aborta al final cualquier sesión registrada -- registrada ANTES de
    aserciones que puedan fallar, para no dejar cupos de admisión pegados
    (self-heal real vía lease de 4h, pero no hay motivo para depender de
    eso: un leak acá contaminaría otros tests de admisión que sí corren en
    la misma suite, como confirmó en vivo un primer intento de este mismo
    archivo)."""
    opened = []
    yield opened
    for session_id, token in opened:
        client.post(f"/uploads/{session_id}/abort", headers=auth_headers(token))


def test_admission_503_carries_retry_after_header_over_real_http(client, _abort_all):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]

    # Llenar el cupo POR USUARIO (default 3) sin completar/abortar nada.
    # OJO: a diferencia de /auth/login (envuelto en {"data": ...}),
    # /uploads/initiate devuelve el schema `UploadInitiateResponse` directo,
    # sin envoltorio -- confirmado en vivo con curl.
    for i in range(settings.MAX_CONCURRENT_LARGE_UPLOADS_PER_USER):
        resp = _initiate(client, token, f"retry_after_{i}.bin")
        # Registrar ANTES de assert -- si el assert de abajo falla, la
        # sesión igual queda marcada para abort en el fixture.
        session_id = _session_id_or_none(resp) if resp.status_code == 201 else None
        if session_id:
            _abort_all.append((session_id, token))
        assert resp.status_code == 201, f"No se pudo abrir sesión {i}: {resp.status_code} {resp.text}"

    # La próxima tiene que dar 503 -- y el header Retry-After tiene que
    # llegar ÍNTEGRO al cliente (el bug lo descartaba en el camino).
    blocked = _initiate(client, token, "retry_after_blocked.bin")
    assert blocked.status_code == 503
    assert blocked.headers.get("retry-after") == "30", (
        f"Retry-After ausente o incorrecto -- headers recibidos: {dict(blocked.headers)}"
    )


def test_admission_503_retry_after_survives_alongside_cors_headers(client, _abort_all):
    """Con un Origin válido en el request, ambos sets de headers (CORS +
    Retry-After) tienen que convivir en la misma respuesta -- ninguno pisa
    al otro."""
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]

    allowed_origin = settings.BACKEND_CORS_ORIGINS[0] if settings.BACKEND_CORS_ORIGINS else None
    assert allowed_origin, "Se necesita al menos un origin en BACKEND_CORS_ORIGINS para este test"
    origin_header = {"Origin": allowed_origin}

    for i in range(settings.MAX_CONCURRENT_LARGE_UPLOADS_PER_USER):
        resp = _initiate(client, token, f"cors_retry_{i}.bin", extra_headers=origin_header)
        session_id = _session_id_or_none(resp) if resp.status_code == 201 else None
        if session_id:
            _abort_all.append((session_id, token))
        assert resp.status_code == 201, f"No se pudo abrir sesión {i}: {resp.status_code} {resp.text}"

    blocked = _initiate(client, token, "cors_retry_blocked.bin", extra_headers=origin_header)
    assert blocked.status_code == 503
    assert blocked.headers.get("retry-after") == "30"
    assert blocked.headers.get("access-control-allow-origin") == allowed_origin
    assert blocked.headers.get("access-control-allow-credentials") == "true"
