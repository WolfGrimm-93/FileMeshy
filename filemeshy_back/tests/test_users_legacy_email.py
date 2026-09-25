"""Regresión: un usuario legado con dominio reservado (ej. *.local) ya
guardado en la BD no debe romper `GET /users` (500 por EmailStr en el schema
de RESPUESTA). La ENTRADA sigue rechazando esos dominios."""
import uuid

from sqlalchemy import text

from conftest import DEFAULT_PASSWORD, auth_headers, make_real_admin, register_user


def test_list_users_serializes_legacy_reserved_domain_email(client, db_session):
    _, admin_token = make_real_admin(client, db_session)

    legacy = register_user(client)
    legacy_email = f"legacy-usuario-{uuid.uuid4().hex[:8]}@dominio.local"
    db_session.execute(
        text("UPDATE users SET email = :new WHERE email = :old"),
        {"new": legacy_email, "old": legacy["email"]},
    )
    db_session.commit()
    try:
        resp = client.get(
            "/users", headers=auth_headers(admin_token), params={"search": legacy_email, "limit": 50}
        )
        assert resp.status_code == 200, resp.text
        emails = [u["email"] for u in resp.json()["items"]]
        assert legacy_email in emails

        # Segunda llamada: la respuesta cacheada tampoco debe romper.
        resp2 = client.get(
            "/users", headers=auth_headers(admin_token), params={"search": legacy_email, "limit": 50}
        )
        assert resp2.status_code == 200, resp2.text
        assert legacy_email in [u["email"] for u in resp2.json()["items"]]
    finally:
        # Limpieza: devolver el usuario a un email válido y desactivarlo.
        db_session.rollback()
        db_session.execute(
            text("UPDATE users SET email = :old, is_active = false WHERE email = :new"),
            {"new": legacy_email, "old": legacy["email"]},
        )
        db_session.commit()


def test_registration_input_still_rejects_reserved_domain(client):
    resp = client.post(
        "/auth/register",
        json={
            "email": "legacy-usuario@dominio.local",
            "first_name": "Legacy",
            "last_name": "User",
            "password": DEFAULT_PASSWORD,
        },
    )
    assert resp.status_code == 422, resp.text
