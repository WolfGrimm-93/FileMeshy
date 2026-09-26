"""Ronda 12b -- contrato del avatar.

Bug: PUT /users/{id} con `avatar` base64/data-URI (> 500 caracteres) -> 500
(VARCHAR(500)); además POST /users/{id}/avatar exigía users.edit, así que un
usuario normal no podía subir su propia foto. Contrato:
  * subir foto: POST /api/v1/users/{user_id}/avatar, multipart, campo `file`;
    responde 200 con el usuario; `avatar` = URL pública lista para <img src>.
  * PUT /users/{id} solo acepta en `avatar` una referencia de storage (o "" / null
    para borrarla); data-URI/base64 o > 500 caracteres -> 422 legible."""
import base64
import io
from types import SimpleNamespace

from PIL import Image

from conftest import auth_headers, login_user, register_user


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (10, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


def _fetch(public_url: str):
    """GET del objeto por el endpoint INTERNO de MinIO (la URL pública apunta al puerto
    publicado en el host, inaccesible desde el contenedor de tests)."""
    import httpx

    from app.core.config import settings

    key_path = public_url.split("/filemeshy-media/", 1)[1]
    return httpx.get(f"{settings.MINIO_ENDPOINT.rstrip('/')}/{settings.MINIO_BUCKET}/{key_path}", timeout=10)


def _user(client):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    body = client.get("/auth/me", headers=auth_headers(token)).json()
    return token, (body.get("data") or body)["id"]


def test_normal_user_can_upload_own_avatar_and_gets_public_url(client):
    token, uid = _user(client)
    resp = client.post(f"/users/{uid}/avatar", headers=auth_headers(token),
                       files={"file": ("yo.png", io.BytesIO(_png()), "image/png")})
    assert resp.status_code == 200, resp.text
    url = resp.json()["avatar"]
    assert url.startswith("http") and f"user_{uid}" in url and url.endswith(".webp")
    # El GET devuelve la misma URL pública.
    got = client.get(f"/users/{uid}", headers=auth_headers(token))
    assert got.status_code == 200 and got.json()["avatar"] == url


def test_user_cannot_upload_avatar_for_someone_else(client):
    token_a, _ = _user(client)
    _, uid_b = _user(client)
    resp = client.post(f"/users/{uid_b}/avatar", headers=auth_headers(token_a),
                       files={"file": ("x.png", io.BytesIO(_png()), "image/png")})
    assert resp.status_code == 403


def test_put_with_data_uri_is_422_with_helpful_message_not_500(client):
    token, uid = _user(client)
    data_uri = "data:image/png;base64," + base64.b64encode(_png() * 20).decode()
    assert len(data_uri) > 500
    resp = client.put(f"/users/{uid}", headers=auth_headers(token), json={"avatar": data_uri})
    assert resp.status_code == 422, resp.text
    assert "POST /api/v1/users/{user_id}/avatar" in resp.text


def test_put_with_overlong_or_foreign_reference_is_422(client):
    token, uid = _user(client)
    assert client.put(f"/users/{uid}", headers=auth_headers(token), json={"avatar": "a" * 600}).status_code == 422
    assert client.put(f"/users/{uid}", headers=auth_headers(token),
                      json={"avatar": "https://evil.example.org/x.png"}).status_code == 422


def test_put_with_foreign_storage_references_is_422(client, db_session):
    """ALTO-3: por PUT el avatar solo puede borrarse o repetir el valor ACTUAL. Antes
    cualquier clave sin esquema pasaba (`files/...`, el avatar de otro usuario) y quedaba
    apuntando a un objeto ajeno."""
    token_a, uid_a = _user(client)
    _, uid_b = _user(client)
    for value in (
        f"files/{uid_a}/secreto.pdf",
        f"avatars/user_{uid_b}/x.webp",
        f"avatars/user_{uid_a}/inventado.webp",  # ni siquiera es propio y existente
        "https://evil.example.org/x.png",
        "http://localhost:58102.evil.com/filemeshy-media/avatars/x.webp",
        "javascript:alert(1)",
    ):
        r = client.put(f"/users/{uid_a}", headers=auth_headers(token_a), json={"avatar": value})
        assert r.status_code == 422, (value, r.status_code, r.text)
    got = client.get(f"/users/{uid_a}", headers=auth_headers(token_a)).json()
    assert got["avatar"] is None


def test_put_can_repeat_current_avatar_and_clear_it(client):
    token, uid = _user(client)
    up = client.post(f"/users/{uid}/avatar", headers=auth_headers(token),
                     files={"file": ("yo.png", io.BytesIO(_png()), "image/png")})
    assert up.status_code == 200
    current = up.json()["avatar"]
    same = client.put(f"/users/{uid}", headers=auth_headers(token), json={"avatar": current, "first_name": "Otro"})
    assert same.status_code == 200 and same.json()["avatar"] == current
    cleared = client.put(f"/users/{uid}", headers=auth_headers(token), json={"avatar": ""})
    assert cleared.status_code == 200 and cleared.json()["avatar"] is None


def test_register_cannot_set_avatar(client):
    from conftest import unique_email

    r = client.post("/auth/register", json={"email": unique_email(), "first_name": "A", "last_name": "B",
                                            "password": "Pytest123!", "avatar": "files/x/y.pdf"})
    assert r.status_code == 422, r.text


def test_avatar_upload_never_deletes_objects_outside_own_prefix(client, db_session):
    """El avatar de A en BD apunta (dato legado o malicioso) al avatar de B; subir uno nuevo
    NO debe borrar el objeto de B."""
    from sqlalchemy import text

    token_a, uid_a = _user(client)
    token_b, uid_b = _user(client)
    rb = client.post(f"/users/{uid_b}/avatar", headers=auth_headers(token_b),
                     files={"file": ("b.png", io.BytesIO(_png()), "image/png")})
    url_b = rb.json()["avatar"]
    assert _fetch(url_b).status_code == 200
    key_b = url_b.split("/filemeshy-media/")[1]
    db_session.execute(text("UPDATE users SET avatar = :k WHERE id = :u"), {"k": key_b, "u": uid_a})
    db_session.commit()
    up = client.post(f"/users/{uid_a}/avatar", headers=auth_headers(token_a),
                     files={"file": ("a.png", io.BytesIO(_png()), "image/png")})
    assert up.status_code == 200, up.text
    assert _fetch(url_b).status_code == 200, "se borró un objeto ajeno"


def test_invalid_upload_keeps_previous_avatar(client):
    token, uid = _user(client)
    ok = client.post(f"/users/{uid}/avatar", headers=auth_headers(token),
                     files={"file": ("yo.png", io.BytesIO(_png()), "image/png")})
    url = ok.json()["avatar"]
    bad = client.post(f"/users/{uid}/avatar", headers=auth_headers(token),
                      files={"file": ("x.png", io.BytesIO(b"esto no es una imagen" * 5), "image/png")})
    assert bad.status_code == 400
    assert client.get(f"/users/{uid}", headers=auth_headers(token)).json()["avatar"] == url
    assert _fetch(url).status_code == 200  # el objeto anterior sigue existiendo


def test_oversized_upload_is_413_and_old_avatar_replaced_at_the_end(client):
    token, uid = _user(client)
    first = client.post(f"/users/{uid}/avatar", headers=auth_headers(token),
                        files={"file": ("1.png", io.BytesIO(_png()), "image/png")}).json()["avatar"]
    big = client.post(f"/users/{uid}/avatar", headers=auth_headers(token),
                      files={"file": ("big.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024 + 10)), "image/png")})
    assert big.status_code == 413, big.text
    assert _fetch(first).status_code == 200
    second = client.post(f"/users/{uid}/avatar", headers=auth_headers(token),
                         files={"file": ("2.png", io.BytesIO(_png()), "image/png")}).json()["avatar"]
    assert second != first
    assert _fetch(second).status_code == 200
    assert _fetch(first).status_code == 404  # el viejo se borra AL FINAL


def test_avatar_content_type_comes_from_validated_format_not_client_header(client):
    token, uid = _user(client)
    up = client.post(f"/users/{uid}/avatar", headers=auth_headers(token),
                     files={"file": ("yo.png", io.BytesIO(_png()), "image/svg+xml")})  # header mentiroso
    assert up.status_code == 400 or up.status_code == 200
    if up.status_code == 200:
        ctype = _fetch(up.json()["avatar"]).headers.get("content-type", "")
        assert ctype.startswith("image/webp") or ctype.startswith("image/png"), ctype


def test_avatar_key_of_only_returns_keys_inside_own_prefix():
    from app.core.config import settings
    from app.users.router import _avatar_key_of

    uid = "0000-uid"
    mk = lambda a: SimpleNamespace(id=uid, avatar=a)  # noqa: E731
    assert _avatar_key_of(mk(None)) is None
    assert _avatar_key_of(mk(f"avatars/user_{uid}/a.webp")) == f"avatars/user_{uid}/a.webp"
    assert _avatar_key_of(mk(f"http://x/{settings.MINIO_BUCKET}/avatars/user_{uid}/a.webp")) == f"avatars/user_{uid}/a.webp"
    for foreign in ("files/otro/x.pdf", "avatars/user_otro/a.webp", f"avatars/user_{uid}/../../x", "https://x/otro-bucket/a"):
        assert _avatar_key_of(mk(foreign)) is None, foreign


def test_is_minio_url_compares_exact_origin():
    from urllib.parse import urlparse

    from app.core.config import settings
    from app.files.service import is_minio_url

    base = (settings.MINIO_PUBLIC_URL or settings.MINIO_ENDPOINT).rstrip("/")
    origin = urlparse(base)
    assert is_minio_url(f"{base}/filemeshy-media/avatars/x.webp")
    assert not is_minio_url(f"{base}.evil.com/x")
    assert not is_minio_url(f"{origin.scheme}://{origin.hostname}:{(origin.port or 80) + 1}/x")
    assert not is_minio_url(f"{origin.scheme}://evil.com/{origin.hostname}/x")
    for bad in ("data:image/png;base64,AAAA", "javascript:alert(1)", "/static/x.png", "", "ftp://x/y"):
        assert not is_minio_url(bad), bad
    assert is_minio_url("avatars/user_1/x.webp")
