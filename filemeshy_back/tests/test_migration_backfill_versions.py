"""Regresión -- backfill de `file_versions` para archivos preexistentes
(Ronda 4, migración `c1d9e5f3a7b2`).

Hallazgo real de la revisión adversarial de frontend (2026-09-20, severidad
alta, pérdida de datos silenciosa): la migración originalmente solo creaba
la tabla `file_versions`, sin backfill -- cualquier `File` que ya existía
ANTES de esta ronda quedaba sin ninguna fila en `file_versions`, rompiendo
la invariante "un archivo SIEMPRE tiene al menos una versión" que documenta
`app/files/models.py::FileVersion`. Peor: si alguien subía una versión
nueva sobre uno de esos archivos "viejos", `get_max_version_number` daba 0
-> la próxima quedaba numerada "versión 1" y el contenido ORIGINAL se
perdía para siempre sin aviso (el `storage_key` viejo quedaba huérfano en
MinIO, sin ningún rastro).

Este test simula exactamente ese escenario: crea un `File` directo por SQL
(sin pasar por `POST /files/upload`, que SIEMPRE crea la versión 1 -- así
se simula un archivo que ya existía antes de que el concepto de versión
existiera), corre la MISMA función de backfill que la migración real
invoca desde `upgrade()` (importada directo del archivo de la migración,
no reimplementada acá -- así el test se rompe de verdad si el backfill
real deja de hacer lo que promete, en vez de validar una reimplementación
paralela que puede desincronizarse), y confirma el estado resultante vía
la API real."""
import importlib.util
import uuid
from pathlib import Path

from conftest import auth_headers, login_user, register_user

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations"
    / "versions"
    / "c1d9e5f3a7b2_add_file_versions.py"
)


def _load_backfill_function():
    spec = importlib.util.spec_from_file_location("migration_c1d9e5f3a7b2", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._backfill_pre_existing_files_as_version_1


def _register_login(client):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    return creds, token


def _insert_pre_existing_file(db_session, *, owner_id, deleted: bool = False, size_bytes: int = 12345) -> tuple[str, str]:
    """Inserta un `File` directo por SQL, simulando un archivo que ya
    existía ANTES de Ronda 4 -- a propósito NO pasa por `POST /files/upload`
    (que ahora siempre crea la versión 1), para reproducir el estado real
    de cualquier archivo subido en Rondas 1-3, antes de que `file_versions`
    existiera."""
    from sqlalchemy import text

    file_id = str(uuid.uuid4())
    storage_key = f"files/{owner_id}/pytest_pre_existente_{uuid.uuid4().hex[:10]}.bin"
    deleted_at_sql = "now()" if deleted else "NULL"

    db_session.execute(
        text(
            f"""
            INSERT INTO files
                (id, name, folder_id, owner_id, storage_key, size_bytes, mime_type,
                 created_at, updated_at, deleted_at, is_favorite)
            VALUES
                (:id, :name, NULL, :owner_id, :storage_key, :size_bytes, :mime_type,
                 now(), now(), {deleted_at_sql}, false)
            """
        ),
        {
            "id": file_id,
            "name": "pytest_archivo_pre_ronda4.bin",
            "owner_id": owner_id,
            "storage_key": storage_key,
            "size_bytes": size_bytes,
            "mime_type": "application/octet-stream",
        },
    )
    db_session.commit()
    return file_id, storage_key


def test_backfill_creates_version_1_for_files_that_predate_versioning(client, db_session):
    creds, token = _register_login(client)
    size_bytes = 54321
    file_id, storage_key = _insert_pre_existing_file(db_session, owner_id=creds["user"]["id"], size_bytes=size_bytes)

    # Confirma la premisa: el archivo "viejo" NO tiene ninguna versión
    # todavía -- es justo lo que rompía sin el backfill.
    versions_before = client.get(f"/files/{file_id}/versions", headers=auth_headers(token))
    assert versions_before.status_code == 200, versions_before.text
    assert versions_before.json() == []

    # Corre la MISMA función que invoca `upgrade()` en la migración real.
    backfill = _load_backfill_function()
    rows_inserted = backfill(db_session.connection())
    db_session.commit()
    assert rows_inserted >= 1

    versions_after = client.get(f"/files/{file_id}/versions", headers=auth_headers(token))
    assert versions_after.status_code == 200, versions_after.text
    versions = versions_after.json()
    assert len(versions) == 1
    version = versions[0]
    assert version["version_number"] == 1
    assert version["size_bytes"] == size_bytes
    assert version["mime_type"] == "application/octet-stream"
    # `created_by_id` = el dueño del archivo (no hay forma de saber quién
    # subió el contenido original antes de que este concepto existiera).
    assert version["created_by_id"] == creds["user"]["id"]

    # El archivo también sigue siendo restaurable/versionable con normalidad
    # a partir de acá -- `get_max_version_number` ya no da 0.
    get_file_resp = client.get(f"/files/{file_id}", headers=auth_headers(token))
    assert get_file_resp.status_code == 200, get_file_resp.text


def test_backfill_skips_soft_deleted_files(client, db_session):
    """Un archivo YA en la papelera al momento de correr la migración no se
    backfillea -- no importa para versionado futuro (ver docstring de la
    función real en la migración)."""
    from sqlalchemy import text

    creds, _token = _register_login(client)
    file_id, _storage_key = _insert_pre_existing_file(db_session, owner_id=creds["user"]["id"], deleted=True)

    backfill = _load_backfill_function()
    backfill(db_session.connection())
    db_session.commit()

    count = db_session.execute(
        text("SELECT COUNT(*) FROM file_versions WHERE file_id = :id"), {"id": file_id}
    ).scalar()
    assert count == 0
