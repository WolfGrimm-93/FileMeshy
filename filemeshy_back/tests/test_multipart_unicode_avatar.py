"""Ronda 12 (E2) -- python-multipart 0.0.18 -> 0.0.32.

La 0.0.30 cambió el parseo de cabeceras (RFC 2231, `filename*=UTF-8''...`).
Estos tests van por HTTP real (fixture `client`, httpx -> uvicorn) y confirman
que un nombre de archivo con caracteres no ASCII llega intacto, y que la
subida de avatar (otro consumidor de multipart) sigue funcionando.
"""
from __future__ import annotations

import io
import urllib.parse

from PIL import Image

from conftest import auth_headers, login_user, make_real_admin, register_user

UNICODE_NAME = "ñandú 日本 é.txt"


def _token(client):
    creds = register_user(client)
    return creds, login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]


def test_upload_unicode_filename_arrives_intact(client):
    """Nombre enviado como UTF-8 crudo en `filename="..."` (lo que hace httpx y
    la mayoría de los navegadores)."""
    _, token = _token(client)
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": (UNICODE_NAME, io.BytesIO(b"hola unicode"), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == UNICODE_NAME
    # Y el detalle persistido también lo devuelve igual.
    detail = client.get(f"/files/{resp.json()['id']}", headers=auth_headers(token))
    assert detail.status_code == 200 and detail.json()["name"] == UNICODE_NAME


def test_upload_rfc2231_filename_star_is_rejected_cleanly(client):
    """Variante `filename*=UTF-8''<percent-encoded>` (RFC 2231/5987): con
    python-multipart 0.0.18 se decodificaba a `filename`; desde la 0.0.30 la
    parte deja de tratarse como archivo. Ningun navegador la envia en
    multipart/form-data (usan `filename="..."` en UTF-8 crudo, cubierto arriba),
    asi que se acepta el cambio -- este test fija el comportamiento nuevo: 4xx
    limpio (nunca 5xx) y sin crear ningun archivo."""
    _, token = _token(client)
    boundary = "----pytestboundary123"
    encoded = urllib.parse.quote(UNICODE_NAME, safe="")
    body = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"file\"; filename*=UTF-8\'\'{encoded}\r\n"
        "Content-Type: text/plain\r\n\r\n"
        "contenido rfc2231\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    resp = client.post(
        "/files/upload",
        headers={**auth_headers(token), "Content-Type": f"multipart/form-data; boundary={boundary}"},
        content=body,
    )
    assert 400 <= resp.status_code < 500, resp.text
    listing = client.get("/files", headers=auth_headers(token))
    assert listing.status_code == 200
    assert UNICODE_NAME not in listing.text


def _me_id(client, token) -> str:
    body = client.get("/auth/me", headers=auth_headers(token)).json()
    return (body.get("data") or body)["id"]


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


def test_avatar_upload_works(client, db_session):
    creds, token = make_real_admin(client, db_session)
    user_id = _me_id(client, token)
    resp = client.post(
        f"/users/{user_id}/avatar",
        headers=auth_headers(token),
        files={"file": ("avatar ñ.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["avatar"]


def test_avatar_rejects_non_image(client, db_session):
    creds, token = make_real_admin(client, db_session)
    user_id = _me_id(client, token)
    resp = client.post(
        f"/users/{user_id}/avatar",
        headers=auth_headers(token),
        files={"file": ("x.png", io.BytesIO(b"no soy una imagen"), "image/png")},
    )
    assert resp.status_code == 400
