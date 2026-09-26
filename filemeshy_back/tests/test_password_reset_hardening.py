"""Ronda 12c -- endurecimiento del flujo de reset de contraseña (revisión adversarial).

ALTO-1  carrera en /verify: el tope de 5 intentos se supera con requests concurrentes
ALTO-2  enumeración de usuarios en /request (cookie/tiempo distintos)
MEDIO-1 IP real en el flujo de reset
MEDIO-3 /confirm concurrente: dos confirmaciones con el mismo token
MEDIO-5 aviso al dueño tras el cambio
BAJO    ceil del Retry-After, mensajes del limitador
Todo por HTTP real (httpx contra el servidor vivo) salvo donde se indica."""
from __future__ import annotations

import threading
from collections import Counter
from types import SimpleNamespace

import httpx
from sqlalchemy import text

from app.auth.service import CodeHashService

from conftest import BASE_URL, _clear_rate_limit_keys, auth_headers, login_user, register_user

API = f"{BASE_URL}/api/v1"
KNOWN = "482913"


def _request(email):
    c = httpx.Client(base_url=API, timeout=20.0)
    r = c.post("/auth/password-reset/request", json={"email": email})
    return c, r


def _set_known_code(db_session, session_id):
    db_session.execute(
        text("UPDATE password_reset_sessions SET code_hash = :h WHERE session_id = :s"),
        {"h": CodeHashService.hash_code(KNOWN), "s": session_id},
    )
    db_session.commit()


def _verified_token(db_session, email):
    """request + verify por HTTP -> (token JWT, session_id)."""
    c, r = _request(email)
    assert r.status_code == 200, r.text
    sid = c.cookies.get("filemeshy_password_reset_session")
    _set_known_code(db_session, sid)
    v = c.post("/auth/password-reset/verify", json={"code": KNOWN})
    assert v.status_code == 200, v.text
    return c.cookies.get("filemeshy_password_reset_token"), sid


def _barrier_run(n, fn):
    barrier = threading.Barrier(n)
    out = [None] * n

    def worker(i):
        barrier.wait()
        out[i] = fn(i)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return out


# ---- ALTO-1 ------------------------------------------------------------------

def test_concurrent_wrong_codes_never_exceed_five_attempts(client, db_session):
    email = register_user(client)["email"]
    _clear_rate_limit_keys()
    c, r = _request(email)
    sid = c.cookies.get("filemeshy_password_reset_session")
    _set_known_code(db_session, sid)
    wrong = [f"{100000 + i:06d}" for i in range(30)]

    def go(i):
        with httpx.Client(base_url=API, timeout=30.0, cookies={"filemeshy_password_reset_session": sid}) as cc:
            return cc.post("/auth/password-reset/verify", json={"code": wrong[i]}).status_code

    statuses = Counter(_barrier_run(30, go))
    assert statuses[400] <= 5, statuses               # como mucho 5 "incorrecto"
    assert statuses[400] + statuses[429] == 30, statuses  # el resto, bloqueado (429)
    db_session.expire_all()
    attempts = db_session.execute(
        text("SELECT code_attempts FROM password_reset_sessions WHERE session_id = :s"), {"s": sid}
    ).scalar_one()
    assert attempts == 5

    # El código CORRECTO después del bloqueo también se rechaza.
    late = c.post("/auth/password-reset/verify", json={"code": KNOWN})
    assert late.status_code == 429
    assert late.headers.get("retry-after", "").isdigit()
    verified = db_session.execute(
        text("SELECT code_verified FROM password_reset_sessions WHERE session_id = :s"), {"s": sid}
    ).scalar_one()
    assert not verified


# ---- ALTO-2 ------------------------------------------------------------------

def _cookie_attrs(response):
    raw = response.headers.get("set-cookie", "")
    parts = [p.strip() for p in raw.split(";")]
    name, _, value = parts[0].partition("=")
    return name, len(value), sorted(p.lower() for p in parts[1:])


def test_request_response_identical_for_existing_and_missing_user(client):
    email = register_user(client)["email"]
    _clear_rate_limit_keys()
    _, existing = _request(email)
    _, missing = _request(f"noexiste_{email}")
    assert existing.status_code == missing.status_code == 200
    assert existing.json() == missing.json()
    assert "set-cookie" in missing.headers, "el email inexistente también debe setear la cookie (falsa)"
    assert _cookie_attrs(existing) == _cookie_attrs(missing)


def test_verify_with_fake_cookie_behaves_like_wrong_code_on_real_session(client, db_session):
    email = register_user(client)["email"]
    _clear_rate_limit_keys()
    real, _ = _request(email)
    fake, _ = _request(f"noexiste_{email}")
    _set_known_code(db_session, real.cookies.get("filemeshy_password_reset_session"))
    # Pasan unos segundos entre crear la sesión y los intentos: con el Retry-After viejo
    # (real = expires_at - now ≈ 896, falsa = 900 fijo) la diferencia se hace visible.
    import time
    time.sleep(4)

    def attempts(c):
        return [c.post("/auth/password-reset/verify", json={"code": "000000"}) for _ in range(6)]

    real_rs, fake_rs = attempts(real), attempts(fake)
    assert [r.status_code for r in real_rs] == [r.status_code for r in fake_rs] == [400] * 5 + [429]
    assert [r.json()["status"] for r in real_rs] == [r.json()["status"] for r in fake_rs]
    # Ronda 12d: cuerpo COMPLETO y headers idénticos (nombres y valores), incluido Retry-After:
    # antes real ≈ 896 y falsa "900" fijo -> 900 delataba al usuario inexistente.
    for a, b in zip(real_rs, fake_rs):
        assert a.json() == b.json()
        assert a.status_code == b.status_code
        ignore = {"date", "content-length", "retry-after"}
        ha = {k: v for k, v in a.headers.items() if k not in ignore}
        hb = {k: v for k, v in b.headers.items() if k not in ignore}
        assert ha == hb
        assert ("retry-after" in a.headers) == ("retry-after" in b.headers)
    ra, rb = int(real_rs[-1].headers["retry-after"]), int(fake_rs[-1].headers["retry-after"])
    assert abs(ra - rb) <= 2 and ra <= 900 and rb <= 900


def test_reset_request_sends_email_outside_the_request_path(db_session, monkeypatch):
    """El envío SMTP va a BackgroundTasks: dentro del handler NO se llama."""
    from fastapi import BackgroundTasks, Response

    from app.auth import router as auth_router
    from app.auth.schemas import PasswordResetRequest
    from app.core.database import SessionLocal
    from app.notifications.service import EmailService

    _clear_rate_limit_keys()
    calls = []
    monkeypatch.setattr(EmailService, "send_password_reset_code", staticmethod(lambda **kw: calls.append(kw) or True))
    user_email = db_session.execute(text("SELECT email FROM users WHERE is_active AND email LIKE 'pytest\\_%@example.com' LIMIT 1")).scalar_one()
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={"user-agent": "pytest"}, cookies={})
    bg = BackgroundTasks()
    db = SessionLocal()
    try:
        resp = auth_router.request_password_reset(
            PasswordResetRequest(email=user_email), request, Response(), bg, db
        )
    finally:
        db.close()
    assert resp.data == {"expires_in_minutes": 15}
    assert calls == [], "el email se envió DENTRO del request"
    assert len(bg.tasks) == 1
    _clear_rate_limit_keys()


# ---- MEDIO-3 -----------------------------------------------------------------

def test_concurrent_confirm_only_one_wins_and_other_sessions_are_invalidated(client, db_session):
    creds = register_user(client)
    email = creds["email"]
    _clear_rate_limit_keys()
    token, sid = _verified_token(db_session, email)
    _clear_rate_limit_keys()
    token2, sid2 = _verified_token(db_session, email)  # otra sesión verificada del MISMO usuario

    def go(i):
        r = httpx.post(f"{API}/auth/password-reset/confirm",
                       json={"new_password": f"Nueva{i}Clave99", "reset_token": token}, timeout=30)
        return r.status_code

    statuses = Counter(_barrier_run(10, go))
    assert statuses[200] == 1, statuses
    assert statuses[200] + statuses[400] == 10, statuses

    # El token verificado de la OTRA sesión ya no sirve.
    r2 = httpx.post(f"{API}/auth/password-reset/confirm",
                    json={"new_password": "OtraClave1234", "reset_token": token2}, timeout=20)
    assert r2.status_code == 400, r2.text
    used = db_session.execute(
        text("SELECT bool_and(is_used) FROM password_reset_sessions WHERE user_id = "
             "(SELECT id FROM users WHERE email = :e)"), {"e": email}
    ).scalar_one()
    assert used is True


# ---- MEDIO-5 -----------------------------------------------------------------

def test_password_reset_notifies_owner_with_valid_route(client, db_session):
    creds = register_user(client)
    _clear_rate_limit_keys()
    token, _ = _verified_token(db_session, creds["email"])
    r = httpx.post(f"{API}/auth/password-reset/confirm",
                   json={"new_password": "NuevaClave456", "reset_token": token}, timeout=20)
    assert r.status_code == 200, r.text
    new_token = login_user(client, creds["email"], "NuevaClave456").json()["data"]["access_token"]
    items = client.get("/notifications", headers=auth_headers(new_token)).json()["items"]
    sec = [n for n in items if n["type"] == "seguridad"]
    assert sec and sec[0]["action_url"] == "/preferencias"
    assert "NuevaClave456" not in str(sec[0])  # sin secretos


def test_notify_flag_is_respected(monkeypatch):
    from app.auth import router as auth_router
    from app.configuration import repository as cfg_repo

    monkeypatch.setattr(cfg_repo.security_policies, "get_active",
                        staticmethod(lambda db: SimpleNamespace(notify_on_password_change=False)))
    assert auth_router._should_notify_password_change(None) is False
    monkeypatch.setattr(cfg_repo.security_policies, "get_active", staticmethod(lambda db: None))
    assert auth_router._should_notify_password_change(None) is True


# ---- BAJO --------------------------------------------------------------------

def test_lock_message_rounds_up_and_retry_after_matches():
    from app.auth.service import _format_lock_message, retry_after_seconds

    assert _format_lock_message(61) == "Demasiados intentos. Intenta en 2 minutos"
    assert retry_after_seconds(_format_lock_message(61)) >= 61
    assert retry_after_seconds(_format_lock_message(3601)) >= 3601


def test_password_reset_free_text_detail_is_returned_as_message():
    from fastapi import FastAPI, HTTPException
    from starlette.testclient import TestClient

    from app.api.v1.exception_handlers import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/password-reset/libre")
    def libre():
        raise HTTPException(429, detail="Demasiadas solicitudes. Intenta en 5 segundos")

    @app.get("/password-reset/conocido")
    def conocido():
        raise HTTPException(400, detail="invalid_code")

    with TestClient(app) as c:
        r = c.get("/password-reset/libre")
        assert r.status_code == 429
        assert r.json()["message"] == "Demasiadas solicitudes. Intenta en 5 segundos"
        assert "desconocido" not in r.text.lower()
        k = c.get("/password-reset/conocido")
        assert k.json()["status"] == "invalid_code" and "desconocido" not in k.text.lower()


def test_no_raw_429_with_free_text_left_in_app():
    """Todo 429 con texto del limitador pasa por `too_many_requests` (lleva Retry-After)."""
    import pathlib
    import re

    root = pathlib.Path("/app/app")
    if not root.exists():
        root = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders = []
    for py in root.rglob("*.py"):
        for i, line in enumerate(py.read_text().splitlines(), 1):
            if re.search(r"HTTPException\(status_code=(status\.HTTP_429_TOO_MANY_REQUESTS|429), detail=rl_", line):
                offenders.append(f"{py.name}:{i}")
    assert not offenders, offenders
