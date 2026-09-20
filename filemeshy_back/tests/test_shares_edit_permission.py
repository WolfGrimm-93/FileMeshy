"""Ronda 3 -- compartir granular: `permission='edit'` en un share de carpeta
dirigido a un usuario.

Con `edit`, el destinatario puede subir un archivo nuevo dentro de la
carpeta compartida (`POST /shares/{id}/files`) -- la cuota se descuenta del
DUEÑO real de la carpeta, nunca del destinatario. Con `view` (el default),
el mismo intento debe dar 403.
"""
import io

from conftest import auth_headers, grant_permission, login_user, register_user


def _register_login(client, db_session, *, permissions=()):
    creds = register_user(client)
    for perm in permissions:
        grant_permission(db_session, creds["email"], perm)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    return creds, token


def _create_folder(client, token, name):
    resp = client.post("/folders", headers=auth_headers(token), json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_directed_folder_share(client, token, folder_id, recipient_email, permission):
    resp = client.post(
        f"/folders/{folder_id}/shares",
        headers=auth_headers(token),
        json={"shared_with_email": recipient_email, "permission": permission},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _my_quota_bytes_used(client, token) -> int:
    resp = client.get("/storage-quotas/me", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["bytes_used"]


def test_edit_permission_lets_recipient_upload_and_charges_owner_quota(client, db_session):
    creds_a, token_a = _register_login(client, db_session, permissions=["shares.create", "folders.create"])
    creds_b, token_b = _register_login(client, db_session)  # B: solo el rol USER por defecto (ya trae files.upload)

    folder = _create_folder(client, token_a, "pytest_carpeta_editable")
    share = _create_directed_folder_share(client, token_a, folder["id"], creds_b["email"], "edit")
    assert share["permission"] == "edit"

    bytes_used_a_before = _my_quota_bytes_used(client, token_a)
    bytes_used_b_before = _my_quota_bytes_used(client, token_b)

    content = b"contenido subido por B dentro de la carpeta de A"
    upload_resp = client.post(
        f"/shares/{share['id']}/files",
        headers=auth_headers(token_b),
        files={"file": ("pytest_subido_por_b.txt", io.BytesIO(content), "text/plain")},
    )
    assert upload_resp.status_code == 201, upload_resp.text
    new_file = upload_resp.json()
    assert new_file["folder_id"] == folder["id"]
    assert new_file["owner_id"] == creds_a["user"]["id"]  # el archivo queda a nombre del DUEÑO de la carpeta
    assert new_file["size_bytes"] == len(content)

    # El archivo aparece en el listado de A...
    listing_resp = client.get(
        "/files", params={"folder_id": folder["id"]}, headers=auth_headers(token_a)
    )
    assert listing_resp.status_code == 200, listing_resp.text
    listed_names = [f["name"] for f in listing_resp.json()["files"]]
    assert "pytest_subido_por_b.txt" in listed_names

    # ...la cuota se descontó de A...
    bytes_used_a_after = _my_quota_bytes_used(client, token_a)
    assert bytes_used_a_after == bytes_used_a_before + len(content)

    # ...y NO de B.
    bytes_used_b_after = _my_quota_bytes_used(client, token_b)
    assert bytes_used_b_after == bytes_used_b_before


def test_view_permission_forbids_recipient_upload(client, db_session):
    creds_a, token_a = _register_login(client, db_session, permissions=["shares.create", "folders.create"])
    creds_b, token_b = _register_login(client, db_session)

    folder = _create_folder(client, token_a, "pytest_carpeta_solo_lectura")
    share = _create_directed_folder_share(client, token_a, folder["id"], creds_b["email"], "view")
    assert share["permission"] == "view"

    upload_resp = client.post(
        f"/shares/{share['id']}/files",
        headers=auth_headers(token_b),
        files={"file": ("pytest_no_deberia_subir.txt", io.BytesIO(b"x"), "text/plain")},
    )
    assert upload_resp.status_code == 403, upload_resp.text


def test_edit_permission_lets_recipient_replace_file_content(client, db_session):
    """Ronda 4: `PUT /shares/{id}/content` fue refactorizado para reusar la
    MISMA lógica de "crear versión nueva" que `POST /files/{id}/versions` --
    el reemplazo vía share ahora también queda versionado (con
    `created_by_id` = el destinatario, no el dueño) y YA NO libera la cuota
    del tamaño viejo (antes de esta ronda sí lo hacía: liberaba el tamaño
    viejo y reservaba solo el nuevo). El blob viejo se conserva como
    historial real, así que la cuota del dueño ahora refleja la SUMA de
    ambas versiones."""
    creds_a, token_a = _register_login(client, db_session, permissions=["shares.create"])
    creds_b, token_b = _register_login(client, db_session)

    old_content = b"version vieja"
    upload_resp = client.post(
        "/files/upload",
        headers=auth_headers(token_a),
        files={"file": ("pytest_archivo_editable.txt", io.BytesIO(old_content), "text/plain")},
    )
    assert upload_resp.status_code == 201, upload_resp.text
    file_obj = upload_resp.json()

    share_resp = client.post(
        f"/files/{file_obj['id']}/shares",
        headers=auth_headers(token_a),
        json={"shared_with_email": creds_b["email"], "permission": "edit"},
    )
    assert share_resp.status_code == 201, share_resp.text
    share = share_resp.json()

    bytes_used_a_before_replace = _my_quota_bytes_used(client, token_a)

    new_content = b"version nueva subida por B"
    replace_resp = client.put(
        f"/shares/{share['id']}/content",
        headers=auth_headers(token_b),
        files={"file": ("nombre_ignorado.txt", io.BytesIO(new_content), "text/plain")},
    )
    assert replace_resp.status_code == 200, replace_resp.text
    updated_file = replace_resp.json()
    assert updated_file["id"] == file_obj["id"]
    assert updated_file["size_bytes"] == len(new_content)

    download_resp = client.get(f"/files/{file_obj['id']}/download", headers=auth_headers(token_a))
    assert download_resp.status_code == 200, download_resp.text

    # Ronda 4 -- la cuota de A (el DUEÑO real) ahora refleja la SUMA de las
    # dos versiones (vieja + nueva), NO solo la nueva: el blob viejo se
    # conserva como historial y nunca se libera.
    bytes_used_a_after_replace = _my_quota_bytes_used(client, token_a)
    assert bytes_used_a_after_replace == bytes_used_a_before_replace + len(new_content)

    # Ronda 4 -- el reemplazo vía share queda versionado: 2 entradas de
    # historial, la más reciente subida por B (el destinatario), no por A.
    versions_resp = client.get(f"/files/{file_obj['id']}/versions", headers=auth_headers(token_a))
    assert versions_resp.status_code == 200, versions_resp.text
    versions = versions_resp.json()
    assert len(versions) == 2
    assert [v["version_number"] for v in versions] == [2, 1]
    assert versions[0]["size_bytes"] == len(new_content)
    assert versions[0]["created_by_id"] == creds_b["user"]["id"]
    assert versions[1]["size_bytes"] == len(old_content)
    assert versions[1]["created_by_id"] == creds_a["user"]["id"]
