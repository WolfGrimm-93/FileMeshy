"""Ronda 12d -- si la notificación del cambio de contraseña falla, /confirm igual responde
200 (la contraseña ya está commiteada) y no se manda un segundo email."""
from types import SimpleNamespace

import httpx
from sqlalchemy import text
from starlette.testclient import TestClient

from app.auth.service import JWTResetService

from conftest import BASE_URL, DEFAULT_PASSWORD, register_user

API = f"{BASE_URL}/api/v1"


def _verified_session_token(db_session, email):
    """Sesión de reset ya verificada + su JWT (se arma directo: el flujo request/verify ya lo cubre
    test_password_reset_hardening)."""
    import uuid

    uid = db_session.execute(text("SELECT id FROM users WHERE email=:e"), {"e": email}).scalar_one()
    sid = str(uuid.uuid4())
    db_session.execute(
        text("INSERT INTO password_reset_sessions (id, session_id, user_id, email, code_hash, expires_at, "
             "code_attempts, code_verified, is_used) VALUES (gen_random_uuid(), :s, :u, :e, 'x', "
             "now() + interval '10 minutes', 0, true, false)"),
        {"s": sid, "u": uid, "e": email},
    )
    db_session.commit()
    return JWTResetService.generate_reset_token(uid, sid, email)


def test_confirm_returns_200_even_if_notification_fails_and_sends_one_email(client, db_session, monkeypatch):
    from app.main import app
    from app.notifications import repository as notif_repo
    from app.notifications.service import EmailService
    from app.worker.tasks import email as email_tasks

    email = register_user(client)["email"]
    token = _verified_session_token(db_session, email)

    def boom(db, *a, **k):
        # Falla REAL de BD: deja la transacción abortada (InFailedSqlTransaction) y la sesión
        # exige rollback; sin él, cualquier acceso ORM posterior lanza PendingRollbackError.
        db.execute(text("SELECT * FROM tabla_que_no_existe_pytest"))

    monkeypatch.setattr(notif_repo.notification, "create", boom)
    notices, task_calls = [], []
    monkeypatch.setattr(EmailService, "send_password_changed_notice", staticmethod(lambda **kw: notices.append(kw) or True))
    monkeypatch.setattr(email_tasks.send_notification_email, "delay", lambda *a, **k: task_calls.append(a))

    with TestClient(app) as c:
        r = c.post("/api/v1/auth/password-reset/confirm", json={"new_password": "NuevaClave456", "reset_token": token})
    assert r.status_code == 200, r.text
    assert httpx.post(f"{API}/auth/login", json={"email": email, "password": "NuevaClave456"}, timeout=10).status_code == 200
    assert httpx.post(f"{API}/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}, timeout=10).status_code in (400, 401)
    assert len(notices) == 1, "debe salir exactamente UN email de aviso"
    assert task_calls == [], "create_notification no debe despachar un segundo email"


def _db_failure(db, *a, **k):
    db.execute(text("SELECT * FROM tabla_que_no_existe_pytest"))


def test_create_notification_rolls_back_session_on_failure(db_session, monkeypatch):
    from app.notifications import repository as notif_repo
    from app.worker.tasks.notification_helpers import create_notification

    uid = db_session.execute(text("SELECT id FROM users LIMIT 1")).scalar_one()
    monkeypatch.setattr(notif_repo.notification, "create", _db_failure)
    ok = create_notification(db_session, uid, "t", "m", "seguridad", "info")
    assert ok is False
    assert db_session.execute(text("SELECT 1")).scalar_one() == 1  # la sesión sigue utilizable
    _ = SimpleNamespace
