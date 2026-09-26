"""Ronda 12 (B2) -- GET /admin/config/email sin configuracion.

Antes: 404 (ruido de consola para un estado normal). Ahora: 200 con
`{"message": "Sin configuracion de email", "configured": false, "data": {}}`.
Consumidor confirmado: filemeshy_front `getEmailConfig` (unico).

La BD del stack es compartida, asi que la lectura de la categoria `email` se
sustituye por datos controlados (solo eso; el handler, el mapeo y el
enmascarado corren de verdad)."""
from types import SimpleNamespace

from sqlalchemy import text

from conftest import auth_headers, make_real_admin


def _cfg(key, *, string=None, number=None, encrypted=False, data_type="string"):
    return SimpleNamespace(
        config_key=key, value_string=string, value_number=number, value_boolean=None,
        value_json=None, is_encrypted=encrypted, data_type=data_type,
    )


def _patch(monkeypatch, rows):
    from app.configuration import router as cfg_router

    monkeypatch.setattr(cfg_router.crud_system_configuration, "get_by_category", lambda db, category: rows)


def test_empty_email_config_returns_200_with_empty_data(client, db_session, monkeypatch):
    _, token = make_real_admin(client, db_session)
    # El monkeypatch corre en el proceso de test, no en el servidor: se llama
    # al handler directo con una sesion real.
    _patch(monkeypatch, [])
    from app.configuration.router import get_email_config

    body = get_email_config(db=db_session, current_user=None)
    assert body["data"] == {}
    assert body["configured"] is False
    assert body["message"] == "Sin configuración de email"


def test_email_config_with_data_masks_password_and_casts_ports(client, db_session, monkeypatch):
    _patch(monkeypatch, [
        _cfg("email_smtp_host", string="smtp.example.com"),
        _cfg("email_smtp_password", string="cifrado-fernet", encrypted=True),
        _cfg("email_smtp_secure_port", number=465.00, data_type="number"),
    ])
    from app.configuration.router import get_email_config

    body = get_email_config(db=db_session, current_user=None)
    assert body["configured"] is True
    assert body["data"]["smtp_host"] == "smtp.example.com"
    assert body["data"]["smtp_password"] == "****"
    assert body["data"]["smtp_secure_port"] == 465 and isinstance(body["data"]["smtp_secure_port"], int)


def test_email_config_endpoint_over_http_is_200_for_admin_and_403_for_user(client, db_session):
    _, admin_token = make_real_admin(client, db_session)
    resp = client.get("/admin/config/email", headers=auth_headers(admin_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "data" in body and isinstance(body["data"], dict) and "configured" in body
    # No depende de "cómo esté la BD hoy": el resultado tiene que ser
    # coherente con las filas reales de la categoría email (sin modificarlas).
    rows = db_session.execute(
        text("SELECT count(*) FROM system_configuration WHERE CAST(config_category AS text) = 'email'")
    ).scalar_one()
    assert body["configured"] is (rows > 0)
    assert bool(body["data"]) is (rows > 0)
    assert "****" in str(body["data"].get("smtp_password", "****"))  # nunca en claro

    from conftest import login_user, register_user

    creds = register_user(client)
    user_token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    assert client.get("/admin/config/email", headers=auth_headers(user_token)).status_code == 403


# ---- Fase 4: enmascarado por nombre de clave y valores falsy ---------------

def test_email_config_masks_password_even_when_not_flagged_encrypted(db_session, monkeypatch):
    """Fila email_smtp_password con is_encrypted=False (ej. creada por el POST
    genérico): antes salía EN CLARO."""
    _patch(monkeypatch, [_cfg("email_smtp_password", string="clave-en-claro", encrypted=False)])
    from app.configuration.router import get_email_config

    body = get_email_config(db=db_session, current_user=None)
    assert body["data"]["smtp_password"] == "****"
    assert "clave-en-claro" not in str(body)


def test_email_config_keeps_false_and_zero_values(db_session, monkeypatch):
    row_false = _cfg("email_smtp_use_tls", data_type="boolean")
    row_false.value_boolean = False
    _patch(monkeypatch, [row_false, _cfg("email_smtp_insecure_port", number=0, data_type="number"),
                         _cfg("email_smtp_secure_port", number=465, data_type="number")])
    from app.configuration.router import get_email_config

    data = get_email_config(db=db_session, current_user=None)["data"]
    assert data["smtp_use_tls"] is False
    assert data["smtp_insecure_port"] == 0
    assert data["smtp_secure_port"] == 465 and isinstance(data["smtp_secure_port"], int)


def test_generic_config_endpoints_mask_secrets(db_session, monkeypatch):
    """GET /admin/config/category/{c} devolvía el valor de filas cifradas; y
    /all no enmascaraba por nombre de clave."""
    from app.configuration import router as cfg_router

    rows = [
        _cfg("smtp_password", string="secreto1", encrypted=False),
        _cfg("otra_clave", string="secreto2", encrypted=True),
        _cfg("password_min_length", number=8, data_type="number"),
    ]
    monkeypatch.setattr(cfg_router.crud_system_configuration, "get_by_category", lambda db, category: rows)
    for r in rows:
        r.config_name, r.config_category, r.version, r.updated_at = r.config_key, "security", 1, None
    monkeypatch.setattr(cfg_router.crud_system_configuration, "get_all", lambda db: rows)

    by_cat = {i["key"]: i["value"] for i in cfg_router.get_config_by_category("security", db=db_session, current_user=None)["data"]}
    all_ = {i["key"]: i["value"] for i in cfg_router.get_all_configs(db=db_session, current_user=None)["data"]}
    for out in (by_cat, all_):
        assert out["smtp_password"] == "****" and out["otra_clave"] == "****"
        assert out["password_min_length"] == 8  # política, no secreto
