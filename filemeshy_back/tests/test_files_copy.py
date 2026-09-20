"""`POST /files/{id}/copy` -- Ronda 1 del hito de Drive avanzado.

El caso más importante de este archivo es el IDOR: un usuario nunca debe
poder copiar un archivo ajeno pasando su ID directamente, mismo criterio que
ya prueba `test_files_idor.py` para ver/descargar/borrar (`_get_owned_file`
en app/files/router.py, 404 -- no 403, para no filtrar ni la existencia del
recurso).
"""
import io

from conftest import auth_headers, grant_permission, login_user, register_user


def _register_and_login(client):
    creds = register_user(client)
    login_data = login_user(client, creds["email"], creds["password"]).json()["data"]
    return creds, login_data["access_token"]


def _upload(client, token, filename="pytest_original.txt", content=b"contenido original de A"):
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_copy_own_file_creates_new_file_with_different_id(client):
    _, token = _register_and_login(client)
    original = _upload(client, token)

    resp = client.post(f"/files/{original['id']}/copy", headers=auth_headers(token))
    assert resp.status_code == 201, resp.text
    copy = resp.json()

    assert copy["id"] != original["id"]
    assert copy["name"] == "pytest_original.txt (copia)"
    assert copy["size_bytes"] == original["size_bytes"]
    assert copy["mime_type"] == original["mime_type"]
    assert copy["owner_id"] == original["owner_id"]
    assert copy["folder_id"] == original["folder_id"]
    assert copy["is_favorite"] is False

    # El original sigue intacto -- copiar no lo modifica ni lo mueve.
    still_original = client.get(f"/files/{original['id']}", headers=auth_headers(token))
    assert still_original.status_code == 200
    assert still_original.json()["name"] == "pytest_original.txt"

    # Ambos aparecen en el listado -- son dos filas reales distintas.
    listing = client.get("/files", headers=auth_headers(token))
    names = [f["name"] for f in listing.json()["files"]]
    assert names.count("pytest_original.txt") == 1
    assert names.count("pytest_original.txt (copia)") == 1


def test_copy_to_another_folder_keeps_original_name(client, db_session):
    creds, token = _register_and_login(client)
    original = _upload(client, token, filename="pytest_para_mover.txt")

    # POST /folders exige folders.create -- el rol USER por defecto no lo
    # trae (ver ROLE_PERMISSIONS_CANONICAL), mismo ajuste puntual que el
    # resto de la suite usa para llegar al código real bajo prueba.
    grant_permission(db_session, creds["email"], "folders.create")

    folder_resp = client.post(
        "/folders", headers=auth_headers(token), json={"name": "pytest_destino"}
    )
    assert folder_resp.status_code == 201, folder_resp.text
    dest_folder_id = folder_resp.json()["id"]

    resp = client.post(
        f"/files/{original['id']}/copy",
        headers=auth_headers(token),
        json={"folder_id": dest_folder_id},
    )
    assert resp.status_code == 201, resp.text
    copy = resp.json()
    # Destino distinto al del original -> sin sufijo " (copia)".
    assert copy["name"] == "pytest_para_mover.txt"
    assert copy["folder_id"] == dest_folder_id
    assert copy["id"] != original["id"]


def test_user_b_cannot_copy_user_a_file(client):
    """El hallazgo central de este archivo: pasar el ID de un archivo ajeno
    a `/files/{id}/copy` no debe crear ninguna copia -- 403/404, igual que
    el resto de endpoints IDOR-sensibles de este router."""
    creds_a, token_a = _register_and_login(client)
    _, token_b = _register_and_login(client)

    file_a = _upload(client, token_a, filename="pytest_secreto_de_a.txt")

    resp = client.post(f"/files/{file_a['id']}/copy", headers=auth_headers(token_b))
    assert resp.status_code in (403, 404)

    # B no debe ver ninguna copia del archivo de A en su propio listado.
    listing_b = client.get("/files", headers=auth_headers(token_b))
    assert listing_b.status_code == 200
    names_b = {f["name"] for f in listing_b.json()["files"]}
    assert "pytest_secreto_de_a.txt" not in names_b
    assert "pytest_secreto_de_a.txt (copia)" not in names_b

    # El archivo de A sigue existiendo, sin copias extra creadas por B.
    listing_a = client.get("/files", headers=auth_headers(token_a))
    names_a = [f["name"] for f in listing_a.json()["files"]]
    assert names_a.count("pytest_secreto_de_a.txt") == 1
