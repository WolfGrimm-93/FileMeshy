"""Favoritos (`is_favorite`) y orden/filtro de listado (`sort_by`, `sort_dir`,
`favorites_only`) en `GET /files` -- Ronda 1 del hito de Drive avanzado.

Dos cosas se verifican:
1. Marcar un archivo como favorito vía `PATCH /files/{id}` y que
   `favorites_only=true` lo devuelva -- y que sin ese flag el listado
   normal también lo siga mostrando (favoritos no es una vista aparte que
   excluya al resto).
2. Que `sort_by`/`sort_dir` ordenen de verdad por la columna pedida (acá
   `size_bytes`) y no por el order_by por defecto (`name`) -- se usan
   nombres cuyo orden alfabético es el INVERSO del orden por tamaño para
   que un test que ordenara mal (o ignorara el parámetro) falle.
"""
import io

from conftest import auth_headers, login_user, register_user


def _register_and_login(client):
    creds = register_user(client)
    login_data = login_user(client, creds["email"], creds["password"]).json()["data"]
    return creds, login_data["access_token"]


def _upload(client, token, filename, content: bytes):
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_favorites_only_filters_but_default_listing_still_shows_it(client):
    # A propósito SIN ningún grant_permission extra: favoritear es una
    # preferencia personal sobre un recurso ya propio (ownership validado por
    # _get_owned_file), no debería exigir "files.rename"/"files.move" -- el
    # rol USER por defecto (solo files.view/files.upload/files.download/
    # folders.view, ver ROLE_PERMISSIONS_CANONICAL en app/core/permissions.py)
    # tiene que alcanzar para marcar/desmarcar favorito. Este test expone en
    # vivo el hallazgo del auditor final de Ronda 1 (2026-09-20): con el gate
    # viejo de la dependency (has_permission(["files.rename","files.move"])),
    # este PATCH devolvía 403 para cualquier usuario sin esos permisos --
    # el caso de uso principal de esta ronda quedaba inutilizable para el rol
    # base. El fix bajó el gate de la dependency a "files.view" y mantiene el
    # chequeo explícito de "files.rename"/"files.move" solo para los campos
    # "name"/"folder_id" (ver update_file en app/files/router.py).
    _, token = _register_and_login(client)

    favorite_file = _upload(client, token, "pytest_favorito.txt", b"contenido favorito")
    other_file = _upload(client, token, "pytest_no_favorito.txt", b"contenido comun")

    patch_resp = client.patch(
        f"/files/{favorite_file['id']}",
        headers=auth_headers(token),
        json={"is_favorite": True},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["is_favorite"] is True

    # Con favorites_only=true, solo aparece el marcado.
    fav_listing = client.get(
        "/files", headers=auth_headers(token), params={"favorites_only": "true"}
    )
    assert fav_listing.status_code == 200
    fav_names = {f["name"] for f in fav_listing.json()["files"]}
    assert fav_names == {"pytest_favorito.txt"}

    # Sin el flag, el listado normal sigue mostrando AMBOS -- favoritos no
    # es una vista que oculte al resto.
    full_listing = client.get("/files", headers=auth_headers(token))
    assert full_listing.status_code == 200
    full_names = {f["name"] for f in full_listing.json()["files"]}
    assert full_names == {"pytest_favorito.txt", "pytest_no_favorito.txt"}
    favorite_entry = next(f for f in full_listing.json()["files"] if f["name"] == "pytest_favorito.txt")
    assert favorite_entry["is_favorite"] is True
    other_entry = next(f for f in full_listing.json()["files"] if f["name"] == "pytest_no_favorito.txt")
    assert other_entry["is_favorite"] is False
    assert other_file["is_favorite"] is False  # control: el schema ya lo trae en la respuesta del upload


def test_favorite_does_not_loosen_rename_or_move_permission_check(client, db_session):
    """Regresión del propio fix: bajar el gate de la dependency de
    `update_file` a "files.view" (para que favoritear no exija
    "files.rename"/"files.move") NO debe aflojar el chequeo real de esos dos
    permisos para los campos que sí los necesitan -- name/folder_id siguen
    evaluándose explícitamente adentro del handler."""
    from conftest import grant_permission

    creds, token = _register_and_login(client)
    file_obj = _upload(client, token, "pytest_sin_permiso.txt", b"contenido")

    # Rol USER por defecto (sin files.rename): favoritear pasa...
    fav_resp = client.patch(
        f"/files/{file_obj['id']}", headers=auth_headers(token), json={"is_favorite": True}
    )
    assert fav_resp.status_code == 200, fav_resp.text

    # ...pero renombrar en un PATCH aparte sigue bloqueado con 403.
    rename_resp = client.patch(
        f"/files/{file_obj['id']}", headers=auth_headers(token), json={"name": "pytest_renombrado.txt"}
    )
    assert rename_resp.status_code == 403, rename_resp.text

    # Mandar los dos campos JUNTOS en el mismo PATCH tampoco cuela -- el
    # chequeo de "name" sigue corriendo aunque "is_favorite" también venga.
    combined_resp = client.patch(
        f"/files/{file_obj['id']}",
        headers=auth_headers(token),
        json={"name": "pytest_renombrado.txt", "is_favorite": False},
    )
    assert combined_resp.status_code == 403, combined_resp.text
    # Y el archivo no quedó a medio modificar por el intento fallido.
    still_there = client.get(f"/files/{file_obj['id']}", headers=auth_headers(token))
    assert still_there.json()["name"] == "pytest_sin_permiso.txt"

    # Con el permiso real otorgado, renombrar sí funciona -- confirma que el
    # chequeo de arriba no está simplemente roto/deshabilitado del todo.
    grant_permission(db_session, creds["email"], "files.rename")
    rename_ok_resp = client.patch(
        f"/files/{file_obj['id']}", headers=auth_headers(token), json={"name": "pytest_renombrado.txt"}
    )
    assert rename_ok_resp.status_code == 200, rename_ok_resp.text
    assert rename_ok_resp.json()["name"] == "pytest_renombrado.txt"


def test_sort_by_size_bytes_desc_overrides_alphabetical_order(client):
    _, token = _register_and_login(client)

    # "pytest_a_..." ordena ANTES que "pytest_z_..." alfabéticamente, pero
    # el archivo "z" es mucho más grande -- si sort_by/sort_dir se ignorara
    # (o cayera al default "name asc"), este test lo detecta.
    small = _upload(client, token, "pytest_a_chico.txt", b"x" * 10)
    big = _upload(client, token, "pytest_z_grande.txt", b"y" * 5000)
    assert small["size_bytes"] < big["size_bytes"]

    resp = client.get(
        "/files",
        headers=auth_headers(token),
        params={"sort_by": "size_bytes", "sort_dir": "desc"},
    )
    assert resp.status_code == 200
    names_in_order = [f["name"] for f in resp.json()["files"]]
    assert names_in_order == ["pytest_z_grande.txt", "pytest_a_chico.txt"]

    # Control: el default (name asc, sin params) da el orden alfabético
    # normal -- confirma que el test anterior de verdad estaba invirtiendo
    # el orden, no que ambos órdenes coinciden por casualidad.
    default_resp = client.get("/files", headers=auth_headers(token))
    assert [f["name"] for f in default_resp.json()["files"]] == ["pytest_a_chico.txt", "pytest_z_grande.txt"]


def test_sort_by_unknown_column_falls_back_to_name_without_error(client):
    """`sort_by` fuera de la whitelist no debe romper el endpoint (whitelist
    en el repository, ver `_resolve_sort_column`) -- cae a "name" en vez de
    tirar 500 o inyectar el string crudo en el ORDER BY."""
    _, token = _register_and_login(client)
    _upload(client, token, "pytest_b.txt", b"b")
    _upload(client, token, "pytest_a.txt", b"a")

    resp = client.get(
        "/files",
        headers=auth_headers(token),
        params={"sort_by": "storage_key; DROP TABLE files;--"},
    )
    assert resp.status_code == 200
    names_in_order = [f["name"] for f in resp.json()["files"]]
    assert names_in_order == ["pytest_a.txt", "pytest_b.txt"]
