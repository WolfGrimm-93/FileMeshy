"""Ronda 12b -- fechas ISO 8601 válidas. Bug: `created_at` de los logs de
auditoría llegaba como `...+00:00Z` (isoformat() de un datetime tz-aware + 'Z'),
inválido para `new Date()` -> columna Fecha/Hora vacía."""
import re
from datetime import datetime, timezone

from app.shared.utils.datetime_iso import to_utc_iso

from conftest import auth_headers, login_user, make_real_admin, register_user

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def test_to_utc_iso_handles_aware_naive_and_none():
    aware = datetime(2026, 9, 26, 14, 47, 41, 115218, tzinfo=timezone.utc)
    assert to_utc_iso(aware) == "2026-09-26T14:47:41.115218Z"
    assert to_utc_iso(datetime(2026, 9, 26, 14, 47, 41)) == "2026-09-26T14:47:41Z"
    assert to_utc_iso(None) is None
    for value in (aware, datetime(2026, 1, 1)):
        out = to_utc_iso(value)
        assert ISO_Z.match(out) and "+00:00" not in out
        datetime.fromisoformat(out.replace("Z", "+00:00"))  # parseable


def test_audit_logs_created_at_is_valid_iso(client, db_session):
    _, token = make_real_admin(client, db_session)
    resp = client.get("/audit-logs", params={"page": 1, "page_size": 20}, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    logs = resp.json()["logs"]
    assert logs, "no hay logs de auditoría para comprobar"
    for log in logs:
        assert ISO_Z.match(log["created_at"]), log["created_at"]
        datetime.fromisoformat(log["created_at"].replace("Z", "+00:00"))


def test_preferences_dates_are_valid_iso_in_get_and_put(client):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    body = client.get("/config/preferences/my-preferences", headers=auth_headers(token)).json()
    # Deben EXISTIR (get_or_create crea la fila): un test que se saltea campos ausentes no comprueba nada.
    for key in ("created_at", "updated_at"):
        assert key in body and body[key], f"falta {key} en el GET de preferencias"
        assert ISO_Z.match(body[key]), body[key]
    put = client.put("/config/preferences/my-preferences", headers=auth_headers(token), json={"theme": "dark"})
    assert put.status_code == 200, put.text
    data = put.json()["data"]
    for key in ("created_at", "updated_at"):
        assert data[key] and ISO_Z.match(data[key]), (key, data.get(key))  # mismo formato `Z` que el GET


def test_users_list_created_at_is_valid_iso(client, db_session):
    _, token = make_real_admin(client, db_session)
    resp = client.get("/users", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    users = body.get("users") or body.get("items") or body.get("data") or []
    assert users, body
    for u in users[:20]:
        assert u.get("created_at") and datetime.fromisoformat(u["created_at"].replace("Z", "+00:00"))
