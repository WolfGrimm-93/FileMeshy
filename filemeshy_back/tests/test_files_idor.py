"""Regresión IDOR (Insecure Direct Object Reference) sobre archivos: un
usuario nunca debe poder ver, descargar ni borrar un archivo de otro usuario
por su ID, aunque lo adivine o lo intercepte -- este es el hallazgo que la
auditoría de seguridad confirmó en vivo.

La protección real vive en `_get_owned_file` (app/files/router.py): compara
`file_obj.owner_id` contra `current_user.id` y devuelve 404 (no 403, a
propósito -- ver comentario del propio código: no filtrar ni siquiera que el
recurso existe) salvo que el usuario sea ADMIN/SUPER_ADMIN.
"""
import io

from conftest import auth_headers, grant_permission, login_user, register_user


def _upload_test_file(client, token, filename="pytest_secreto.txt", content=b"contenido confidencial de user A"):
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _register_and_login(client):
    creds = register_user(client)
    login_data = login_user(client, creds["email"], creds["password"]).json()["data"]
    return creds, login_data["access_token"]


def test_user_cannot_view_other_users_file(client):
    _, token_a = _register_and_login(client)
    _, token_b = _register_and_login(client)

    file_obj = _upload_test_file(client, token_a)
    file_id = file_obj["id"]

    # Dueño puede verlo sin problema (control positivo).
    own_resp = client.get(f"/files/{file_id}", headers=auth_headers(token_a))
    assert own_resp.status_code == 200

    # Usuario B, ajeno al archivo, NO debe poder verlo.
    other_resp = client.get(f"/files/{file_id}", headers=auth_headers(token_b))
    assert other_resp.status_code in (403, 404)


def test_user_cannot_download_other_users_file(client):
    _, token_a = _register_and_login(client)
    _, token_b = _register_and_login(client)

    file_obj = _upload_test_file(client, token_a)
    file_id = file_obj["id"]

    own_resp = client.get(f"/files/{file_id}/download", headers=auth_headers(token_a))
    assert own_resp.status_code == 200
    assert own_resp.json()["download_url"]

    other_resp = client.get(f"/files/{file_id}/download", headers=auth_headers(token_b))
    assert other_resp.status_code in (403, 404)


def test_user_cannot_delete_other_users_file(client, db_session):
    creds_a, token_a = _register_and_login(client)
    creds_b, token_b = _register_and_login(client)

    file_obj = _upload_test_file(client, token_a)
    file_id = file_obj["id"]

    # El rol USER por defecto no incluye `files.delete` (ver
    # ROLE_PERMISSIONS_CANONICAL en app/core/permissions.py) -- se lo
    # otorgamos puntualmente a B en BD para que el intento de borrar llegue
    # de verdad al chequeo de ownership y no se frene antes en el gate de
    # RBAC (que taparía el resultado que interesa a este test: la
    # protección de ownership en sí, no una restricción de rol aparte).
    grant_permission(db_session, creds_b["email"], "files.delete")

    resp = client.delete(f"/files/{file_id}", headers=auth_headers(token_b))
    assert resp.status_code in (403, 404)

    # El archivo de A debe seguir intacto -- ni borrado ni con deleted_at.
    still_there = client.get(f"/files/{file_id}", headers=auth_headers(token_a))
    assert still_there.status_code == 200
    assert still_there.json()["deleted_at"] is None


def test_user_cannot_list_other_users_root_directory_via_folder_id(client):
    """Sanity adicional: listar el directorio raíz nunca debe filtrar
    archivos/carpetas de otro usuario -- el listado usa siempre el propio
    `current_user.id` como scope salvo que se pida un folder_id puntual
    (que a su vez pasa por _get_owned_folder, mismo criterio de 404)."""
    _, token_a = _register_and_login(client)
    _, token_b = _register_and_login(client)

    _upload_test_file(client, token_a, filename="pytest_solo_de_a.txt")

    listing_b = client.get("/files", headers=auth_headers(token_b))
    assert listing_b.status_code == 200
    names_b = {f["name"] for f in listing_b.json()["files"]}
    assert "pytest_solo_de_a.txt" not in names_b
