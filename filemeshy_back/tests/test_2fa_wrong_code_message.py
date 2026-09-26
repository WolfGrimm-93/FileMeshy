"""Ronda 12b -- código 2FA incorrecto en el login: el BACKEND responde 401 con un
detail claro ("Código incorrecto"). El toast "Refresh token no encontrado" que se
veía en el navegador NO viene de acá (esa cadena solo existe en /auth/refresh sin
cookie): lo produce el interceptor de axios del frontend, que ante ese 401 intenta
un refresh. Este test fija el contrato del backend (status 401 + mensaje claro)."""
from test_2fa_dos_fixed import _get_pre_auth_token, _register_login_and_enable_2fa

from conftest import verify_2fa_login


def test_wrong_2fa_code_is_401_with_clear_message(client):
    creds, _ = _register_login_and_enable_2fa(client)
    pre = _get_pre_auth_token(client, creds)
    resp = verify_2fa_login(client, pre, "000000")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Código incorrecto"
    assert "refresh" not in resp.text.lower()
