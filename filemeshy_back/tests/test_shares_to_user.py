"""Ronda 3 -- compartir granular: share dirigido a un usuario específico
(`shared_with_email` al crear -> `shared_with_user_id` resuelto).

A diferencia del link público, el acceso es SIEMPRE autenticado y por el
propio `id` del share (`GET /shares/with-me`, `GET /shares/{id}`,
`GET /shares/{id}/download/{file_id}`) -- nunca por `/public/shares`. Un
tercero ajeno al share (ni destinatario ni dueño) no debe poder verlo, y el
destinatario recibe una notificación real al crearse el share.
"""
import io

from conftest import auth_headers, grant_permission, login_user, register_user


def _register_login(client, *, with_shares_create=False, db_session=None):
    creds = register_user(client)
    if with_shares_create:
        grant_permission(db_session, creds["email"], "shares.create")
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    return creds, token


def _upload_file(client, token, filename="pytest_compartido_directo.txt", content=b"contenido para B"):
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_share_to_user_visible_downloadable_and_notified(client, db_session):
    creds_a, token_a = _register_login(client, with_shares_create=True, db_session=db_session)
    creds_b, token_b = _register_login(client)
    creds_c, token_c = _register_login(client)  # tercero, ajeno al share

    file_obj = _upload_file(client, token_a)

    share_resp = client.post(
        f"/files/{file_obj['id']}/shares",
        headers=auth_headers(token_a),
        json={"shared_with_email": creds_b["email"]},
    )
    assert share_resp.status_code == 201, share_resp.text
    share = share_resp.json()
    assert share["token"] is None  # share dirigido -- no necesita link público
    assert share["shared_with_user_id"] == creds_b["user"]["id"]
    assert share["shared_with_email"] == creds_b["email"]
    assert share["permission"] == "view"
    share_id = share["id"]

    # B lo ve en su bandeja de "compartidos conmigo" -- con nombre del
    # recurso y quién lo compartió, no solo IDs pelados (hallazgo del agente
    # de frontend: sin esto la UI no podía mostrar nada usable).
    with_me_resp = client.get("/shares/with-me", headers=auth_headers(token_b))
    assert with_me_resp.status_code == 200, with_me_resp.text
    with_me_items = with_me_resp.json()
    with_me_ids = [s["id"] for s in with_me_items]
    assert share_id in with_me_ids
    with_me_share = next(s for s in with_me_items if s["id"] == share_id)
    assert with_me_share["resource_name"] == "pytest_compartido_directo.txt"
    assert with_me_share["resource_type"] == "file"
    assert with_me_share["shared_by_email"] == creds_a["email"]

    # En cambio, crear el share y listar los shares DE un archivo propio
    # (endpoints donde el caller ya conoce el recurso por contexto) NO
    # resuelven estos tres campos -- quedan en None a propósito, ver
    # docstring de `_share_to_out`.
    assert share.get("resource_name") is None
    assert share.get("shared_by_email") is None

    # B puede ver el contenido del share puntual...
    content_resp = client.get(f"/shares/{share_id}", headers=auth_headers(token_b))
    assert content_resp.status_code == 200, content_resp.text
    content_body = content_resp.json()
    assert content_body["type"] == "file"
    assert content_body["name"] == "pytest_compartido_directo.txt"

    # ...y descargarlo.
    download_resp = client.get(
        f"/shares/{share_id}/download/{file_obj['id']}", headers=auth_headers(token_b)
    )
    assert download_resp.status_code == 200, download_resp.text
    assert download_resp.json()["download_url"]

    # C, un tercero sin relación con el share, NO puede verlo -- ni 200 ni
    # una distinción de "existe pero no es tuyo" (403 o 404, no filtra).
    c_resp = client.get(f"/shares/{share_id}", headers=auth_headers(token_c))
    assert c_resp.status_code in (403, 404), c_resp.text

    # El link público de este share no puede usarse -- no tiene token.
    assert content_body.get("download_url")  # control: B sí obtuvo un link firmado real

    # Notificación real para B.
    notif_resp = client.get("/notifications", headers=auth_headers(token_b))
    assert notif_resp.status_code == 200, notif_resp.text
    items = notif_resp.json()["items"]
    matching = [n for n in items if n["type"] == "compartido"]
    assert matching, f"No se encontró notificación 'compartido' para B: {items}"
    assert "pytest_compartido_directo.txt" in matching[0]["message"]


def test_directed_share_not_reachable_via_public_endpoint(client, db_session):
    """Un share dirigido no tiene token -- el link público no puede
    exhibirlo bajo ningún /public/shares/{token} real (no hay token que
    probar, control de sentido: confirma que `token` efectivamente vino
    `None` en la respuesta y no una cadena vacía usable)."""
    creds_a, token_a = _register_login(client, with_shares_create=True, db_session=db_session)
    creds_b, _ = _register_login(client)

    file_obj = _upload_file(client, token_a, filename="pytest_solo_directo.txt")
    share_resp = client.post(
        f"/files/{file_obj['id']}/shares",
        headers=auth_headers(token_a),
        json={"shared_with_email": creds_b["email"]},
    )
    assert share_resp.status_code == 201, share_resp.text
    assert share_resp.json()["token"] is None


def test_share_to_unknown_email_returns_404(client, db_session):
    creds_a, token_a = _register_login(client, with_shares_create=True, db_session=db_session)
    file_obj = _upload_file(client, token_a, filename="pytest_email_inexistente.txt")

    resp = client.post(
        f"/files/{file_obj['id']}/shares",
        headers=auth_headers(token_a),
        json={"shared_with_email": "no-existe-nadie-con-este-email@example.com"},
    )
    assert resp.status_code == 404, resp.text
