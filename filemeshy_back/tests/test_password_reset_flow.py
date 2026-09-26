"""Ronda 12b -- flujo COMPLETO de reset de contraseña por HTTP real.

Bug (preexistente desde el commit inicial): POST /auth/password-reset/confirm
hacía `int(token_payload["sub"])` sobre un UUID -> 500, así que el reseteo nunca
podía completarse (y /verify pasaba un kwarg inexistente al log de auditoría).

Cómo se obtiene el código: /request lo genera y lo manda por email (o solo lo
loguea en DEBUG); no hay forma limpia de leerlo, así que después de pedirlo POR
HTTP se reemplaza en la BD el hash de esa sesión real por el de un código
conocido (CodeHashService.hash_code, el mismo mecanismo del servidor)."""
from __future__ import annotations

import uuid

import httpx
import jwt
import pytest
from sqlalchemy import text

from app.auth.service import CodeHashService, JWTResetService
from app.core.config import settings

from conftest import BASE_URL, DEFAULT_PASSWORD, register_user

API = f"{BASE_URL}/api/v1"
NEW_PASSWORD = "NuevaClave456"
KNOWN_CODE = "482913"


@pytest.fixture
def http():
    # Cliente PROPIO (con cookies): el reset viaja por cookies httpOnly.
    with httpx.Client(base_url=API, timeout=15.0, headers={"X-Real-IP": "10.9.9.9"}) as c:
        yield c


def _request_code(http, db_session, email):
    resp = http.post("/auth/password-reset/request", json={"email": email})
    assert resp.status_code == 200, resp.text
    session_id = http.cookies.get("filemeshy_password_reset_session")
    assert session_id
    db_session.execute(
        text("UPDATE password_reset_sessions SET code_hash = :h WHERE session_id = :s"),
        {"h": CodeHashService.hash_code(KNOWN_CODE), "s": session_id},
    )
    db_session.commit()
    return session_id


def _login(email, password):
    with httpx.Client(base_url=API, timeout=15.0) as c:
        return c.post("/auth/login", json={"email": email, "password": password})


def _clean_rate_limits(email):
    # Ronda 12c: limpia las claves REALES (127.0.0.1, la IP que ve el endpoint); antes se
    # limpiaba la de una IP falsa que el endpoint ignora y el contador real subía entre corridas.
    from conftest import _clear_rate_limit_keys

    _clear_rate_limit_keys()


def test_full_reset_flow_end_to_end(http, client, db_session):
    creds = register_user(client)
    email = creds["email"]
    _clean_rate_limits(email)

    # Sesión previa activa: el reset debe revocarla.
    old_login = _login(email, DEFAULT_PASSWORD)
    assert old_login.status_code == 200
    old_access = old_login.json()["data"]["access_token"]
    # Se USA el access token antes del reset: queda cacheado como "sesión activa" 30 s
    # (MEDIO-2) y aun así tiene que dejar de valer apenas se confirma el reset.
    for _ in range(2):
        assert httpx.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {old_access}"}, timeout=10).status_code == 200

    session_id = _request_code(http, db_session, email)

    ver = http.post("/auth/password-reset/verify", json={"code": KNOWN_CODE})
    assert ver.status_code == 200, ver.text
    token = http.cookies.get("filemeshy_password_reset_token")
    assert token

    conf = http.post("/auth/password-reset/confirm", json={"new_password": NEW_PASSWORD})
    assert conf.status_code == 200, conf.text

    # Login con la nueva contraseña sí, con la vieja no.
    assert _login(email, NEW_PASSWORD).status_code == 200
    assert _login(email, DEFAULT_PASSWORD).status_code in (400, 401)

    # La sesión anterior quedó revocada.
    me = httpx.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {old_access}"}, timeout=10)
    assert me.status_code == 401

    # Uso único: reusar el token -> 4xx (nunca 500) y la contraseña no vuelve a cambiar.
    again = httpx.post(f"{API}/auth/password-reset/confirm",
                       json={"new_password": "OtraClave789", "reset_token": token}, timeout=10)
    assert 400 <= again.status_code < 500, again.text
    assert _login(email, "OtraClave789").status_code in (400, 401)
    used = db_session.execute(
        text("SELECT is_used FROM password_reset_sessions WHERE session_id = :s"), {"s": session_id}
    ).scalar_one()
    assert used is True


def test_wrong_code_is_400_and_five_attempts_lock(http, client, db_session):
    email = register_user(client)["email"]
    _clean_rate_limits(email)
    _request_code(http, db_session, email)
    for _ in range(5):
        assert http.post("/auth/password-reset/verify", json={"code": "000000"}).status_code == 400
    assert http.post("/auth/password-reset/verify", json={"code": KNOWN_CODE}).status_code == 429


def test_expired_session_code_is_rejected(http, client, db_session):
    email = register_user(client)["email"]
    _clean_rate_limits(email)
    session_id = _request_code(http, db_session, email)
    db_session.execute(
        text("UPDATE password_reset_sessions SET expires_at = now() - interval '1 minute' WHERE session_id = :s"),
        {"s": session_id},
    )
    db_session.commit()
    assert http.post("/auth/password-reset/verify", json={"code": KNOWN_CODE}).status_code == 400


def test_confirm_without_verified_code_is_rejected(client, db_session):
    """Un reset_token firmado para una sesión cuyo código NUNCA se verificó no
    debe cambiar la contraseña."""
    creds = register_user(client)
    user_id = db_session.execute(text("SELECT id FROM users WHERE email = :e"), {"e": creds["email"]}).scalar_one()
    sid = str(uuid.uuid4())
    db_session.execute(
        text("INSERT INTO password_reset_sessions (id, session_id, user_id, email, code_hash, expires_at, "
             "code_attempts, code_verified, is_used) VALUES (gen_random_uuid(), :s, :u, :e, 'x', "
             "now() + interval '10 minutes', 0, false, false)"),
        {"s": sid, "u": user_id, "e": creds["email"]},
    )
    db_session.commit()
    token = JWTResetService.generate_reset_token(user_id, sid, creds["email"])
    resp = httpx.post(f"{API}/auth/password-reset/confirm",
                      json={"new_password": NEW_PASSWORD, "reset_token": token}, timeout=10)
    assert 400 <= resp.status_code < 500, resp.text
    assert _login(creds["email"], DEFAULT_PASSWORD).status_code == 200


@pytest.mark.parametrize("sub", ["no-es-uuid", "12345", "", "../../etc"])
def test_malformed_sub_is_4xx_never_500(sub):
    now = 2_000_000_000
    token = jwt.encode(
        {"sub": sub, "session_id": "s", "email": "x@example.com", "scope": "password_reset", "exp": now},
        settings.SECRET_KEY, algorithm="HS256",
    )
    resp = httpx.post(f"{API}/auth/password-reset/confirm",
                      json={"new_password": NEW_PASSWORD, "reset_token": token}, timeout=10)
    assert 400 <= resp.status_code < 500, resp.text


def test_garbage_and_missing_token_is_4xx():
    r1 = httpx.post(f"{API}/auth/password-reset/confirm",
                    json={"new_password": NEW_PASSWORD, "reset_token": "basura"}, timeout=10)
    r2 = httpx.post(f"{API}/auth/password-reset/confirm", json={"new_password": NEW_PASSWORD}, timeout=10)
    assert r1.status_code == 401 and r2.status_code == 400


def test_weak_or_reused_password_is_400(http, client, db_session):
    creds = register_user(client)
    _clean_rate_limits(creds["email"])
    _request_code(http, db_session, creds["email"])
    assert http.post("/auth/password-reset/verify", json={"code": KNOWN_CODE}).status_code == 200
    # Igual a la contraseña actual -> 400 (reuso).
    assert http.post("/auth/password-reset/confirm", json={"new_password": DEFAULT_PASSWORD}).status_code == 400
    # Política débil (validada por el schema) -> 422 legible.
    assert http.post("/auth/password-reset/confirm", json={"new_password": "corta"}).status_code == 422
