"""Regresión -- integridad de cuota en la purga de papelera (Ronda 4).

Bug real encontrado por la revisión adversarial (2026-09-20, severidad alta,
corrompe cuota de OTROS archivos del mismo dueño -- no es IDOR): la purga
calculaba cuánta cuota liberar sumando `size_bytes` de CADA fila de
`file_versions` sin deduplicar por `storage_key`. Como `restore_file_version`
crea una fila de historial NUEVA que reapunta al `storage_key` de una
versión vieja (sin reservar cuota nueva, a propósito -- el blob ya estaba
contado), un archivo con un restore en su historial contaba ese mismo blob
DOS veces al purgar, liberando más cuota de la que ese archivo realmente
tenía reservada y arrastrando cuota de otros archivos intactos del mismo
usuario.

Este test llama a `purge_deleted_files_and_folders` DIRECTO (no hay
endpoint HTTP para la purga -- es una tarea de Celery, se invoca como
función Python normal, síncrona, sin necesitar el broker) porque antes de
esta ronda no había NINGÚN test que la ejercitara -- por eso el bug no lo
agarró la suite."""
import io

from conftest import auth_headers, grant_permission, login_user, register_user


def _register_login_with_delete(client, db_session):
    creds = register_user(client)
    grant_permission(db_session, creds["email"], "files.delete")
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    return creds, token


def _upload(client, token, content: bytes, filename: str = "pytest_purge.txt"):
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload_version(client, token, file_id, content: bytes, filename: str = "pytest_purge_v.txt"):
    resp = client.post(
        f"/files/{file_id}/versions",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _my_quota_bytes_used(client, token) -> int:
    resp = client.get("/storage-quotas/me", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["bytes_used"]


def _force_deleted_31_days_ago(db_session, file_id) -> None:
    from sqlalchemy import text

    db_session.execute(
        text("UPDATE files SET deleted_at = now() - interval '31 days' WHERE id = :id"),
        {"id": file_id},
    )
    db_session.commit()


def test_purge_after_restore_frees_exactly_the_purged_files_quota_not_more(client, db_session):
    """Escenario exacto reportado por la revisión adversarial: un archivo
    con >1 versión + al menos 1 restore, y un SEGUNDO archivo intacto del
    mismo dueño. Purgar el primero debe dejar la cuota EXACTAMENTE en lo que
    corresponde al segundo archivo (que nunca se tocó) -- ni un byte más ni
    menos."""
    _, token = _register_login_with_delete(client, db_session)

    # Archivo 1: 4 versiones de 1000 bytes cada una (bytes reales distintos
    # para no depender de que el contenido sea idéntico) + un restore a la
    # versión 1 -- esto agrega una 5ta fila de historial que reapunta al
    # MISMO storage_key de la versión 1, sin sumar cuota nueva.
    v1_content = b"a" * 1000
    file_1 = _upload(client, token, v1_content)
    for suffix in (b"b", b"c", b"d"):
        _upload_version(client, token, file_1["id"], suffix * 1000)

    versions_resp = client.get(f"/files/{file_1['id']}/versions", headers=auth_headers(token))
    assert versions_resp.status_code == 200, versions_resp.text
    versions = versions_resp.json()
    assert len(versions) == 4
    version_1_id = next(v["id"] for v in versions if v["version_number"] == 1)

    restore_resp = client.post(
        f"/files/{file_1['id']}/versions/{version_1_id}/restore",
        headers=auth_headers(token),
    )
    assert restore_resp.status_code == 200, restore_resp.text

    # Cuota real reservada por el archivo 1: 4 blobs únicos de 1000 bytes
    # cada uno (4000) -- el restore NO agrega bytes nuevos.
    bytes_used_after_file_1 = _my_quota_bytes_used(client, token)
    assert bytes_used_after_file_1 == 4000

    # Archivo 2: intacto, nunca se toca -- su cuota (500 bytes) tiene que
    # sobrevivir intacta a la purga del archivo 1.
    file_2_size = 500
    file_2 = _upload(client, token, b"x" * file_2_size)

    bytes_used_before_purge = _my_quota_bytes_used(client, token)
    assert bytes_used_before_purge == 4000 + file_2_size

    # Soft-delete + forzar antigüedad de papelera del archivo 1 (30+ días).
    delete_resp = client.delete(f"/files/{file_1['id']}", headers=auth_headers(token))
    assert delete_resp.status_code == 204, delete_resp.text
    _force_deleted_31_days_ago(db_session, file_1["id"])

    # Purga real -- se invoca la tarea de Celery directo (síncrono, sin
    # broker), como corre de verdad en producción vía el scheduler.
    from app.worker.tasks.maintenance import purge_deleted_files_and_folders

    result = purge_deleted_files_and_folders(days=30)
    assert result, "la purga no devolvió resultados -- revisar iter_tenant_schemas()"

    # El archivo 1 quedó realmente purgado (fila borrada de verdad).
    get_resp = client.get(f"/files/{file_1['id']}", headers=auth_headers(token))
    assert get_resp.status_code == 404, get_resp.text

    # El archivo 2 sigue intacto y accesible.
    get_file_2_resp = client.get(f"/files/{file_2['id']}", headers=auth_headers(token))
    assert get_file_2_resp.status_code == 200, get_file_2_resp.text

    # LA ASERCIÓN CLAVE: la cuota que queda es EXACTAMENTE la del archivo 2
    # que sigue vivo -- ni un byte más (bug: contaba el blob restaurado dos
    # veces y liberaba de más, arrastrando la cuota del archivo 2) ni menos.
    bytes_used_after_purge = _my_quota_bytes_used(client, token)
    assert bytes_used_after_purge == file_2_size
