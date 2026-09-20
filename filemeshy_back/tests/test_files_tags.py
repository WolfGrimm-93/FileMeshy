"""Asignación de etiquetas a archivos (`PUT /files/{id}/tags`) -- Ronda 2 del
hito de Drive avanzado.

Cubre: asignar etiquetas propias a un archivo propio y que aparezcan
embebidas en `GET /files`, y los DOS casos de IDOR por separado (criterio
"todo o nada" de `_resolve_owned_tags` en app/files/router.py):
1. Usuario B no puede asignarle a un archivo de A una etiqueta de B (el
   archivo no es de B -- ownership del archivo).
2. Usuario B no puede asignarle a un archivo propio una etiqueta que
   pertenece a otro usuario (la etiqueta no es de B -- ownership de la
   etiqueta).
"""
import io

from conftest import auth_headers, login_user, register_user


def _register_and_login(client):
    creds = register_user(client)
    login_data = login_user(client, creds["email"], creds["password"]).json()["data"]
    return creds, login_data["access_token"]


def _upload(client, token, filename, content: bytes = b"contenido pytest"):
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_assign_tags_to_own_file_and_appears_in_listing(client):
    _, token = _register_and_login(client)

    tag1 = client.post("/tags", headers=auth_headers(token), json={"name": "Importante"}).json()
    tag2 = client.post("/tags", headers=auth_headers(token), json={"name": "Urgente"}).json()
    file_obj = _upload(client, token, "pytest_con_tags.txt")

    put_resp = client.put(
        f"/files/{file_obj['id']}/tags",
        headers=auth_headers(token),
        json={"tag_ids": [tag1["id"], tag2["id"]]},
    )
    assert put_resp.status_code == 200, put_resp.text
    returned_ids = {t["id"] for t in put_resp.json()["tags"]}
    assert returned_ids == {tag1["id"], tag2["id"]}

    listing = client.get("/files", headers=auth_headers(token))
    assert listing.status_code == 200
    entry = next(f for f in listing.json()["files"] if f["id"] == file_obj["id"])
    assert {t["id"] for t in entry["tags"]} == {tag1["id"], tag2["id"]}

    # PUT reemplaza el set completo -- no es incremental. Mandar solo tag1
    # debe SACAR tag2, no agregarse a lo que ya había.
    replace_resp = client.put(
        f"/files/{file_obj['id']}/tags",
        headers=auth_headers(token),
        json={"tag_ids": [tag1["id"]]},
    )
    assert replace_resp.status_code == 200, replace_resp.text
    assert [t["id"] for t in replace_resp.json()["tags"]] == [tag1["id"]]

    # Y con una lista vacía, se limpian todas.
    clear_resp = client.put(
        f"/files/{file_obj['id']}/tags", headers=auth_headers(token), json={"tag_ids": []}
    )
    assert clear_resp.status_code == 200, clear_resp.text
    assert clear_resp.json()["tags"] == []


def test_filter_files_by_tag_id(client):
    _, token = _register_and_login(client)

    tag = client.post("/tags", headers=auth_headers(token), json={"name": "FiltroTag"}).json()
    tagged_file = _upload(client, token, "pytest_filtrado.txt")
    other_file = _upload(client, token, "pytest_sin_filtro.txt")

    put_resp = client.put(
        f"/files/{tagged_file['id']}/tags", headers=auth_headers(token), json={"tag_ids": [tag["id"]]}
    )
    assert put_resp.status_code == 200, put_resp.text

    filtered = client.get("/files", headers=auth_headers(token), params={"tag_id": tag["id"]})
    assert filtered.status_code == 200
    filtered_names = {f["name"] for f in filtered.json()["files"]}
    assert filtered_names == {"pytest_filtrado.txt"}
    assert other_file["name"] not in filtered_names


def test_user_b_cannot_tag_user_a_file_even_with_own_tag(client):
    """IDOR #1 -- ownership del ARCHIVO: B no puede tocar un archivo que no
    es suyo, aunque la etiqueta que intente usar sea legítimamente propia."""
    _, token_a = _register_and_login(client)
    _, token_b = _register_and_login(client)

    file_a = _upload(client, token_a, "pytest_archivo_de_a.txt")
    tag_b = client.post("/tags", headers=auth_headers(token_b), json={"name": "TagDeB"}).json()

    attempt = client.put(
        f"/files/{file_a['id']}/tags", headers=auth_headers(token_b), json={"tag_ids": [tag_b["id"]]}
    )
    assert attempt.status_code == 404, attempt.text

    # El archivo de A sigue sin etiquetas -- el intento no se aplicó a medias.
    still_there = client.get(f"/files/{file_a['id']}", headers=auth_headers(token_a))
    assert still_there.json()["tags"] == []


def test_user_b_cannot_tag_own_file_with_user_a_tag(client):
    """IDOR #2 -- ownership de la ETIQUETA: B es dueño del archivo, pero la
    etiqueta que intenta usar es de A -- debe rechazarse igual, sin aplicar
    un subconjunto silencioso."""
    _, token_a = _register_and_login(client)
    _, token_b = _register_and_login(client)

    tag_a = client.post("/tags", headers=auth_headers(token_a), json={"name": "TagDeA"}).json()
    file_b = _upload(client, token_b, "pytest_archivo_de_b.txt")

    attempt = client.put(
        f"/files/{file_b['id']}/tags", headers=auth_headers(token_b), json={"tag_ids": [tag_a["id"]]}
    )
    assert attempt.status_code == 404, attempt.text

    still_there = client.get(f"/files/{file_b['id']}", headers=auth_headers(token_b))
    assert still_there.json()["tags"] == []


def test_mixed_own_and_foreign_tag_ids_rejects_the_whole_request(client):
    """Un id propio mezclado con uno ajeno en el mismo `tag_ids` tampoco
    aplica parcialmente el propio -- todo o nada."""
    _, token_a = _register_and_login(client)
    _, token_b = _register_and_login(client)

    own_tag = client.post("/tags", headers=auth_headers(token_b), json={"name": "PropiaDeB"}).json()
    foreign_tag = client.post("/tags", headers=auth_headers(token_a), json={"name": "DeA"}).json()
    file_b = _upload(client, token_b, "pytest_mixto.txt")

    attempt = client.put(
        f"/files/{file_b['id']}/tags",
        headers=auth_headers(token_b),
        json={"tag_ids": [own_tag["id"], foreign_tag["id"]]},
    )
    assert attempt.status_code == 404, attempt.text

    still_there = client.get(f"/files/{file_b['id']}", headers=auth_headers(token_b))
    assert still_there.json()["tags"] == []
