"""Confirma el fix de `/auth/register` ignorando el flag
`user_registration_enabled` (ver app/auth/router.py::register).

Antes de este fix, un admin podía "apagar" el registro público desde el
panel de configuración (`user_registration_enabled=false`) y
`POST /auth/register` seguía devolviendo 201 igual -- el endpoint nunca leía
ese flag. Usa el mismo endpoint genérico de config que usaría el panel de
admin (`/admin/config/create` + `/admin/config/update/{config_key}`, ver
app/configuration/router.py) para setearlo en false, confirma el 403, y lo
restaura a `true` al terminar (pase o falle el test) para no dejar el resto
del suite -- que registra usuarios en casi todos los demás archivos -- roto.
"""
import pytest

from conftest import DEFAULT_PASSWORD, auth_headers, login_user, unique_email

ADMIN_EMAIL = "audit-admin@example.com"
ADMIN_PASSWORD = "AuditTest123!@#"

CONFIG_KEY = "user_registration_enabled"


def _get_admin_token(client) -> str:
    resp = login_user(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _set_registration_enabled(client, admin_token: str, enabled: bool) -> None:
    payload = {
        "config_key": CONFIG_KEY,
        "config_name": "Registro de usuarios habilitado",
        "config_category": "security",
        "data_type": "boolean",
        "value_boolean": enabled,
    }
    resp = client.put(
        f"/admin/config/update/{CONFIG_KEY}",
        headers=auth_headers(admin_token),
        json=payload,
    )
    # `PUT /admin/config/update/{config_key}` (app/configuration/router.py,
    # fuera del alcance de este fix) envuelve su propio HTTPException(404) en
    # un `except Exception` genérico y lo re-lanza como 400 con el mensaje
    # original adentro -- por eso el chequeo de "no existe todavía" mira el
    # texto, no solo el status code.
    config_not_found = resp.status_code == 404 or (
        resp.status_code == 400 and "no encontrada" in resp.text
    )
    if config_not_found:
        # Todavía no existe la config -- crearla directamente ya en el
        # estado deseado.
        resp = client.post(
            "/admin/config/create",
            headers=auth_headers(admin_token),
            json=payload,
        )
    assert resp.status_code == 200, resp.text


@pytest.fixture
def registration_disabled(client):
    """Deshabilita `user_registration_enabled` para el test y lo restaura a
    `true` al terminar -- pase o falle el test -- para no dejar registrar
    usuarios roto para el resto del suite."""
    admin_token = _get_admin_token(client)
    _set_registration_enabled(client, admin_token, False)
    try:
        yield
    finally:
        _set_registration_enabled(client, admin_token, True)


def test_register_returns_403_when_flag_disabled(client, registration_disabled):
    resp = client.post(
        "/auth/register",
        json={
            "email": unique_email(),
            "first_name": "Pytest",
            "last_name": "Blocked",
            "password": DEFAULT_PASSWORD,
        },
    )
    assert resp.status_code == 403, resp.text


def test_register_works_again_after_flag_restored(client):
    """Sanity extra: confirma que la fixture de arriba de verdad restaura el
    flag -- si no lo hiciera, este test (que corre con la config ya en
    `true` de nuevo) fallaría también."""
    resp = client.post(
        "/auth/register",
        json={
            "email": unique_email(),
            "first_name": "Pytest",
            "last_name": "Restored",
            "password": DEFAULT_PASSWORD,
        },
    )
    assert resp.status_code == 201, resp.text
