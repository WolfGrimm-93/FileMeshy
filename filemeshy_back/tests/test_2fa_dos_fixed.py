"""Confirma el FIX del DoS de 2FA por colisión de prefijo JWT en
`POST /auth/2fa/verify-login` (ver `app/auth/router.py::verify_2fa_login`).

Causa raíz: la clave de rate-limit usaba `pre_auth_token[:16]` -- los
primeros 16 caracteres de CUALQUIER JWT HS256 son siempre el mismo string
(el header base64 fijo `{"alg":"HS256","typ":"JWT"}`), así que ese
componente de la clave era constante sin importar el usuario o la sesión de
login. El límite terminaba siendo compartido por todas las sesiones de
pre-autenticación (detrás de la misma IP, que en este stack de test además
es siempre 127.0.0.1) -- agotar los intentos de UN usuario bloqueaba a
CUALQUIER OTRO. El fix usa el `jti` del pre_auth_token (único por sesión de
login) en la clave.

Este test agota el rate-limit del usuario A a fuerza de códigos incorrectos
y confirma que el usuario B, en una sesión de login totalmente distinta,
puede completar su propio 2FA sin problema.
"""
import pyotp

from app.core.config import settings

from conftest import auth_headers, login_user, register_user, verify_2fa_login


def _register_login_and_enable_2fa(client):
    """Registra un usuario, activa 2FA con un secreto TOTP real y devuelve
    (creds, objeto pyotp.TOTP) -- mismo flujo que test_auth.py::test_2fa_end_to_end."""
    creds = register_user(client)
    login_resp = login_user(client, creds["email"], creds["password"])
    assert login_resp.status_code == 200, login_resp.text
    access_token = login_resp.json()["data"]["access_token"]

    setup_resp = client.post("/auth/2fa/setup", headers=auth_headers(access_token))
    assert setup_resp.status_code == 200, setup_resp.text
    secret = setup_resp.json()["data"]["secret"]
    totp = pyotp.TOTP(secret)

    enable_resp = client.post(
        "/auth/2fa/enable",
        headers=auth_headers(access_token),
        json={"code": totp.now()},
    )
    assert enable_resp.status_code == 200, enable_resp.text

    return creds, totp


def _get_pre_auth_token(client, creds) -> str:
    login_resp = login_user(client, creds["email"], creds["password"])
    assert login_resp.status_code == 200, login_resp.text
    data = login_resp.json()["data"]
    assert data.get("requires_2fa") is True
    return data["pre_auth_token"]


def test_2fa_rate_limit_is_per_session_not_global(client):
    creds_a, _totp_a = _register_login_and_enable_2fa(client)
    creds_b, totp_b = _register_login_and_enable_2fa(client)

    pre_auth_a = _get_pre_auth_token(client, creds_a)

    # Agotar el rate-limit de A con códigos incorrectos -- 1 intento más que
    # el máximo configurado alcanza para que el próximo caiga en 429.
    max_attempts = settings.RATE_LIMIT_MAX_ATTEMPTS
    statuses_a = []
    for _ in range(max_attempts + 1):
        resp = verify_2fa_login(client, pre_auth_a, "000000")
        statuses_a.append(resp.status_code)

    assert 429 in statuses_a, (
        f"No se bloqueó a A tras {max_attempts + 1} códigos incorrectos "
        f"(status codes: {statuses_a}) -- el rate-limit de 2FA no está funcionando."
    )

    # B, en una sesión de login COMPLETAMENTE DISTINTA (jti propio), no debe
    # verse afectado por los intentos fallidos de A -- antes del fix, ambos
    # compartían la misma clave de rate-limit (pre_auth_token[:16] + IP) y B
    # habría recibido 429 acá también.
    pre_auth_b = _get_pre_auth_token(client, creds_b)
    resp_b = verify_2fa_login(client, pre_auth_b, totp_b.now())
    assert resp_b.status_code == 200, (
        f"B quedó bloqueado por el rate-limit agotado de A: "
        f"{resp_b.status_code} {resp_b.text} -- el bug de colisión de prefijo "
        "JWT seguiría existiendo."
    )
