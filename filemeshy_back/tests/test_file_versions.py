"""Ronda 4 -- versionado de archivos.

`upload_file` crea la versión 1 automáticamente. `POST /files/{id}/versions`
sube versiones nuevas SIN pisar el blob viejo (cada una consume cuota real
adicional contra el dueño). `GET /files/{id}/versions` devuelve el historial
completo, más reciente primero. `POST /files/{id}/versions/{version_id}/restore`
vuelve a una versión anterior sin costo de cuota adicional (no sube nada
nuevo, reusa el blob ya existente) y queda como una entrada NUEVA del
historial. Todo el módulo exige ownership del archivo -- IDOR verificado al
final (usuario B no puede ver/subir/restaurar versiones de un archivo de A).
"""
import io

from conftest import auth_headers, login_user, register_user


def _register_login(client):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    return creds, token


def _upload(client, token, content: bytes, filename: str = "pytest_versionado.txt"):
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload_version(client, token, file_id, content: bytes, filename: str = "pytest_v2.txt"):
    return client.post(
        f"/files/{file_id}/versions",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )


def _list_versions(client, token, file_id):
    resp = client.get(f"/files/{file_id}/versions", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _my_quota_bytes_used(client, token) -> int:
    resp = client.get("/storage-quotas/me", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["bytes_used"]


def _current_storage_key(db_session, file_id) -> str:
    """Lee `File.storage_key` DIRECTO de la BD -- `FileOut` nunca lo expone
    (detalle interno), pero el test necesita el dato crudo para confirmar
    que un restore vuelve a apuntar al blob REAL de la versión vieja, no
    solo que `size_bytes` coincide por casualidad."""
    from sqlalchemy import text

    row = db_session.execute(text("SELECT storage_key FROM files WHERE id = :id"), {"id": file_id}).first()
    assert row is not None
    return row[0]


def _read_object_content(storage_key: str) -> bytes:
    """Lee el contenido real de un objeto de MinIO, directo por el cliente
    interno de la app (alcanzable desde dentro del contenedor por
    `MINIO_ENDPOINT`) -- mismo mecanismo que `app.files.router._read_private_object`."""
    from app.core.config import settings
    from app.files.service import _get_client

    client = _get_client()
    obj = client.get_object(Bucket=settings.MINIO_PRIVATE_BUCKET, Key=storage_key)
    return obj["Body"].read()


def test_upload_creates_a_single_initial_version(client):
    _, token = _register_login(client)
    content = b"contenido original"
    file_obj = _upload(client, token, content)

    versions = _list_versions(client, token, file_obj["id"])
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1
    assert versions[0]["size_bytes"] == len(content)
    assert versions[0]["mime_type"] == file_obj["mime_type"]
    assert versions[0]["created_by_id"] == file_obj["owner_id"]
    assert versions[0]["created_by_email"] is not None


def test_uploading_new_versions_accumulates_history_and_quota(client):
    _, token = _register_login(client)

    bytes_used_before = _my_quota_bytes_used(client, token)

    content_v1 = b"v1 - contenido chico"
    file_obj = _upload(client, token, content_v1)

    content_v2 = b"v2 - contenido un poco mas largo que v1"
    resp_v2 = _upload_version(client, token, file_obj["id"], content_v2)
    assert resp_v2.status_code == 201, resp_v2.text
    updated_file_v2 = resp_v2.json()
    assert updated_file_v2["id"] == file_obj["id"]
    assert updated_file_v2["size_bytes"] == len(content_v2)

    content_v3 = b"v3 - el contenido mas largo de las tres versiones subidas en este test"
    resp_v3 = _upload_version(client, token, file_obj["id"], content_v3)
    assert resp_v3.status_code == 201, resp_v3.text
    updated_file_v3 = resp_v3.json()

    # File.size_bytes/mime_type reflejan SIEMPRE la última versión.
    assert updated_file_v3["size_bytes"] == len(content_v3)

    versions = _list_versions(client, token, file_obj["id"])
    assert len(versions) == 3
    # Orden: version_number desc.
    assert [v["version_number"] for v in versions] == [3, 2, 1]
    sizes_by_version = {v["version_number"]: v["size_bytes"] for v in versions}
    assert sizes_by_version[1] == len(content_v1)
    assert sizes_by_version[2] == len(content_v2)
    assert sizes_by_version[3] == len(content_v3)
    # Las tres versiones tienen tamaños distintos entre sí.
    assert len({sizes_by_version[1], sizes_by_version[2], sizes_by_version[3]}) == 3

    # La cuota del dueño refleja la SUMA de las tres versiones (cada blob
    # sigue existiendo en MinIO como historial), no solo la última.
    bytes_used_after = _my_quota_bytes_used(client, token)
    total_expected = len(content_v1) + len(content_v2) + len(content_v3)
    assert bytes_used_after == bytes_used_before + total_expected


def test_restore_version_reverts_file_without_extra_quota_cost(client, db_session):
    _, token = _register_login(client)

    content_v1 = b"contenido de la version 1, la que se va a restaurar"
    file_obj = _upload(client, token, content_v1)

    content_v2 = b"contenido de la version 2, mas reciente"
    resp_v2 = _upload_version(client, token, file_obj["id"], content_v2)
    assert resp_v2.status_code == 201, resp_v2.text

    versions_before_restore = _list_versions(client, token, file_obj["id"])
    assert len(versions_before_restore) == 2
    version_1_id = next(v["id"] for v in versions_before_restore if v["version_number"] == 1)

    bytes_used_before_restore = _my_quota_bytes_used(client, token)

    restore_resp = client.post(
        f"/files/{file_obj['id']}/versions/{version_1_id}/restore",
        headers=auth_headers(token),
    )
    assert restore_resp.status_code == 200, restore_resp.text
    restored_file = restore_resp.json()
    assert restored_file["id"] == file_obj["id"]
    assert restored_file["size_bytes"] == len(content_v1)

    # El archivo restaurado sigue siendo descargable (URL firmada real)...
    download_resp = client.get(f"/files/{file_obj['id']}/download", headers=auth_headers(token))
    assert download_resp.status_code == 200, download_resp.text
    assert download_resp.json()["download_url"]

    # ...y el blob real al que apunta es efectivamente el de la v1 (no solo
    # que `size_bytes` coincide por casualidad) -- confirma que el restore
    # reapunta `storage_key` al blob YA EXISTENTE, sin subir nada nuevo.
    restored_storage_key = _current_storage_key(db_session, file_obj["id"])
    assert _read_object_content(restored_storage_key) == content_v1

    # Se crea una 4ta entrada de historial (evento "se restauró la v1"), sin
    # duplicar el blob -- 3 filas en total: v1, v2, y la restauración de v1.
    versions_after_restore = _list_versions(client, token, file_obj["id"])
    assert len(versions_after_restore) == 3
    assert [v["version_number"] for v in versions_after_restore] == [3, 2, 1]
    restored_entry = versions_after_restore[0]
    assert restored_entry["version_number"] == 3
    assert restored_entry["size_bytes"] == len(content_v1)

    # El restore NO consume cuota adicional -- el blob ya estaba contado.
    bytes_used_after_restore = _my_quota_bytes_used(client, token)
    assert bytes_used_after_restore == bytes_used_before_restore


def test_user_b_cannot_see_upload_or_restore_versions_of_user_a_file(client):
    _, token_a = _register_login(client)
    _, token_b = _register_login(client)

    file_obj = _upload(client, token_a, b"contenido privado de A")

    # B no puede LISTAR el historial de un archivo de A.
    list_resp = client.get(f"/files/{file_obj['id']}/versions", headers=auth_headers(token_b))
    assert list_resp.status_code == 404, list_resp.text

    # B no puede SUBIR una versión nueva de un archivo de A.
    upload_resp = _upload_version(client, token_b, file_obj["id"], b"intento de B")
    assert upload_resp.status_code == 404, upload_resp.text

    # B no puede RESTAURAR ninguna versión de un archivo de A -- ni siquiera
    # adivinando el id real de la versión 1 (obtenido acá solo para probar
    # el IDOR, un atacante real no lo tendría tan fácil).
    versions_of_a = _list_versions(client, token_a, file_obj["id"])
    version_1_id = versions_of_a[0]["id"]
    restore_resp = client.post(
        f"/files/{file_obj['id']}/versions/{version_1_id}/restore",
        headers=auth_headers(token_b),
    )
    assert restore_resp.status_code == 404, restore_resp.text


def test_restore_rejects_version_id_from_another_file(client):
    """`version_id` tiene que pertenecer REALMENTE a `file_id` -- ver
    `file_version_repo.get_by_id_for_file`. Mezclar el id de una versión de
    OTRO archivo propio (mismo dueño, otro `file_id`) también debe dar 404,
    no solo el caso cross-usuario."""
    _, token = _register_login(client)

    file_1 = _upload(client, token, b"archivo uno")
    file_2 = _upload(client, token, b"archivo dos")

    versions_of_file_2 = _list_versions(client, token, file_2["id"])
    version_of_file_2_id = versions_of_file_2[0]["id"]

    restore_resp = client.post(
        f"/files/{file_1['id']}/versions/{version_of_file_2_id}/restore",
        headers=auth_headers(token),
    )
    assert restore_resp.status_code == 404, restore_resp.text
