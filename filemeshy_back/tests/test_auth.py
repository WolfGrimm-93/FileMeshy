"""Regresión de los flujos críticos de autenticación: registro, login exitoso,
login con contraseña incorrecta, y 2FA (TOTP) end-to-end -- setup, activación,
login parcial y verificación con un código TOTP real generado con pyotp.

Corre contra el stack real (Postgres/Redis reales, sin mocks) -- ver
conftest.py para la fixture `client` y los helpers de registro/login.
"""
import pyotp

from conftest import DEFAULT_PASSWORD, auth_headers, login_user, register_user, unique_email, verify_2fa_login


def test_register_success(client):
    result = register_user(client)
    user = result["user"]
    assert user["email"] == result["email"]
    assert "id" in user
    assert user["is_active"] is True
    # El registro público nunca debe poder auto-asignarse otro rol (ver
    # auth/router.py::register: `user_in.role_id = None` a propósito).
    assert user.get("role") in (None, "USER")


def test_register_duplicate_email_rejected(client):
    creds = register_user(client)
    resp = client.post(
        "/auth/register",
        json={
            "email": creds["email"],
            "first_name": "Otro",
            "last_name": "Pytest",
            "password": DEFAULT_PASSWORD,
        },
    )
    assert resp.status_code == 400


def test_login_success(client):
    creds = register_user(client)
    resp = login_user(client, creds["email"], creds["password"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["user"]["email"] == creds["email"]


def test_login_wrong_password_returns_401(client):
    creds = register_user(client)
    resp = login_user(client, creds["email"], "ContraseñaIncorrecta1")
    assert resp.status_code == 401


def test_login_nonexistent_user_returns_401(client):
    resp = login_user(client, unique_email(), "Cualquiera1")
    assert resp.status_code == 401


def test_2fa_end_to_end(client):
    """Flujo completo: setup -> enable (con TOTP real) -> login pide 2FA ->
    verify-login (con TOTP real) devuelve tokens completos."""
    creds = register_user(client)
    login_resp = login_user(client, creds["email"], creds["password"])
    assert login_resp.status_code == 200, login_resp.text
    access_token = login_resp.json()["data"]["access_token"]

    # --- 1) Iniciar configuración 2FA ---
    setup_resp = client.post("/auth/2fa/setup", headers=auth_headers(access_token))
    assert setup_resp.status_code == 200, setup_resp.text
    setup_data = setup_resp.json()["data"]
    secret = setup_data["secret"]
    assert secret
    assert len(setup_data["backup_codes"]) > 0

    # --- 2) Activar con un código TOTP real generado a partir del secreto ---
    totp = pyotp.TOTP(secret)
    enable_resp = client.post(
        "/auth/2fa/enable",
        headers=auth_headers(access_token),
        json={"code": totp.now()},
    )
    assert enable_resp.status_code == 200, enable_resp.text
    assert enable_resp.json()["data"]["enabled"] is True

    # --- 3) Un login nuevo ahora debe quedar en pausa pidiendo 2FA ---
    second_login = login_user(client, creds["email"], creds["password"])
    assert second_login.status_code == 200, second_login.text
    login_data = second_login.json()["data"]
    assert login_data.get("requires_2fa") is True
    pre_auth_token = login_data["pre_auth_token"]

    # --- 4) Completar el login con un código TOTP real ---
    verify_resp = verify_2fa_login(client, pre_auth_token, totp.now())
    assert verify_resp.status_code == 200, verify_resp.text
    final_data = verify_resp.json()["data"]
    assert final_data["access_token"]
    assert final_data["token_type"] == "bearer"
    assert final_data["user"]["email"] == creds["email"]

    # --- 5) El mismo pre_auth_token no debe poder reutilizarse (uso único) ---
    replay_resp = verify_2fa_login(client, pre_auth_token, totp.now())
    assert replay_resp.status_code == 401


def test_2fa_login_wrong_code_rejected(client):
    creds = register_user(client)
    access_token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]

    secret = client.post("/auth/2fa/setup", headers=auth_headers(access_token)).json()["data"]["secret"]
    totp = pyotp.TOTP(secret)
    client.post("/auth/2fa/enable", headers=auth_headers(access_token), json={"code": totp.now()})

    pre_auth_token = login_user(client, creds["email"], creds["password"]).json()["data"]["pre_auth_token"]

    resp = verify_2fa_login(client, pre_auth_token, "000000")
    assert resp.status_code == 401
