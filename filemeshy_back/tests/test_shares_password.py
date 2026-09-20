"""Ronda 3 -- compartir granular: contraseña opcional en un link público.

Un link público (`shared_with_user_id` NULL) sigue siendo anónimo, accedido
por token sin autenticación -- pero si el share tiene `password_hash`, los
dos endpoints públicos (`GET /public/shares/{token}` y
`.../download/{file_id}`) exigen esa contraseña vía el header
`X-Share-Password` (decisión de diseño: NUNCA por query param, para no
dejarla en logs de acceso/historial del navegador/Referer -- ver docstring
de `_verify_share_password` en app/files/router.py).
"""
import io

from conftest import auth_headers, grant_permission, login_user, register_user

SHARE_PASSWORD = "SuperSecreta123!"


def _register_login_with_shares_create(client, db_session):
    creds = register_user(client)
    grant_permission(db_session, creds["email"], "shares.create")
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    return creds, token


def _upload_file(client, token, filename="pytest_con_password.txt", content=b"contenido protegido por password"):
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_public_share_with_password_blocks_and_allows_correctly(client, db_session):
    _, token_a = _register_login_with_shares_create(client, db_session)
    file_obj = _upload_file(client, token_a)

    share_resp = client.post(
        f"/files/{file_obj['id']}/shares",
        headers=auth_headers(token_a),
        json={"password": SHARE_PASSWORD},
    )
    assert share_resp.status_code == 201, share_resp.text
    share = share_resp.json()
    assert share["has_password"] is True
    assert share["token"] is not None
    assert share["permission"] == "view"
    token = share["token"]

    # Sin contraseña -- 401, sin filtrar que el link existe.
    resp_no_pass = client.get(f"/public/shares/{token}")
    assert resp_no_pass.status_code == 401, resp_no_pass.text

    # Contraseña incorrecta -- 401, mismo mensaje que "sin contraseña"
    # (no debe distinguir "falta" de "incorrecta").
    resp_wrong_pass = client.get(
        f"/public/shares/{token}",
        headers={"X-Share-Password": "esta-no-es"},
    )
    assert resp_wrong_pass.status_code == 401, resp_wrong_pass.text
    assert resp_wrong_pass.json()["detail"] == resp_no_pass.json()["detail"]

    # Contraseña correcta -- 200, contenido real.
    resp_ok = client.get(
        f"/public/shares/{token}",
        headers={"X-Share-Password": SHARE_PASSWORD},
    )
    assert resp_ok.status_code == 200, resp_ok.text
    body = resp_ok.json()
    assert body["type"] == "file"
    assert body["name"] == "pytest_con_password.txt"
    assert body["download_url"]

    # El endpoint de descarga exige la MISMA contraseña, independiente del
    # de contenido -- no alcanza con haber pasado el primero.
    resp_dl_no_pass = client.get(f"/public/shares/{token}/download/{file_obj['id']}")
    assert resp_dl_no_pass.status_code == 401, resp_dl_no_pass.text

    resp_dl_wrong = client.get(
        f"/public/shares/{token}/download/{file_obj['id']}",
        headers={"X-Share-Password": "tampoco-es-esta"},
    )
    assert resp_dl_wrong.status_code == 401, resp_dl_wrong.text

    resp_dl_ok = client.get(
        f"/public/shares/{token}/download/{file_obj['id']}",
        headers={"X-Share-Password": SHARE_PASSWORD},
    )
    assert resp_dl_ok.status_code == 200, resp_dl_ok.text
    assert resp_dl_ok.json()["download_url"]


def test_public_share_without_password_still_works_without_header(client, db_session):
    """Regresión: un share SIN password (comportamiento de Hito 2, sin
    cambios) sigue siendo de acceso libre por token -- Ronda 3 no debe
    romper el caso más común."""
    _, token_a = _register_login_with_shares_create(client, db_session)
    file_obj = _upload_file(client, token_a, filename="pytest_sin_password.txt")

    share_resp = client.post(
        f"/files/{file_obj['id']}/shares",
        headers=auth_headers(token_a),
        json={},
    )
    assert share_resp.status_code == 201, share_resp.text
    share = share_resp.json()
    assert share["has_password"] is False

    resp = client.get(f"/public/shares/{share['token']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "pytest_sin_password.txt"
