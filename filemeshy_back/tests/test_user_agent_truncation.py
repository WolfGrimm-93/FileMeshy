"""Fase 4 (Ronda 12) -- User-Agent/IP/endpoint más largos que su columna.

`sessions.user_agent` es String(500): un UA de 600+ caracteres (el cliente lo
controla; uvicorn acepta headers de hasta ~64KB) daba StringDataRightTruncation
-> 500 en el LOGIN con last_login ya commiteado."""
from sqlalchemy import text

from conftest import register_user

LONG_UA = "Mozilla/5.0 " + "X" * 1988  # 2000 caracteres


def test_login_with_2000_char_user_agent_succeeds_and_stores_500(client, db_session):
    creds = register_user(client)
    resp = client.post(
        "/auth/login",
        json={"email": creds["email"], "password": creds["password"]},
        headers={"User-Agent": LONG_UA},
    )
    client.cookies.clear()
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    lengths = db_session.execute(
        text(
            "SELECT length(s.user_agent) FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE u.email = :e ORDER BY s.created_at DESC"
        ),
        {"e": creds["email"]},
    ).scalars().all()
    assert lengths and lengths[0] == 500


def test_second_login_same_long_ua_replaces_previous_session(client, db_session):
    """El filtro 'misma sesión del mismo dispositivo' compara contra el UA ya
    recortado: la segunda sesión invalida la primera (una sola activa)."""
    creds = register_user(client)
    for _ in range(2):
        r = client.post("/auth/login", json={"email": creds["email"], "password": creds["password"]},
                        headers={"User-Agent": LONG_UA})
        client.cookies.clear()
        assert r.status_code == 200, r.text
    db_session.expire_all()
    active = db_session.execute(
        text("SELECT count(*) FROM sessions s JOIN users u ON u.id = s.user_id WHERE u.email = :e AND s.is_active"),
        {"e": creds["email"]},
    ).scalar_one()
    assert active == 1


def test_user_agent_parser_still_reasonable_on_clipped_value():
    from app.auth.models import Session
    from app.auth.schemas import _parse_user_agent

    clipped = Session.clip_user_agent(LONG_UA)
    assert len(clipped) == 500
    assert _parse_user_agent(clipped)[0] in ("desktop", "mobile")
    assert Session.clip_user_agent(None) == "unknown"


def test_audit_log_columns_are_clipped(db_session):
    from app.audit.repository import audit_log

    row = audit_log.create_log(
        db=db_session,
        user_id=None,
        user_email="pytest_clip@example.com",
        action="CREATE",
        table_name="t" * 300,
        record_id="r" * 300,
        ip_address="1" * 100,
        user_agent=LONG_UA,
        endpoint="/" + "e" * 2000,
        method="POST",
    )
    assert len(row.endpoint) == 255 and len(row.ip_address) == 45
    assert len(row.table_name) == 100 and len(row.record_id) == 100
