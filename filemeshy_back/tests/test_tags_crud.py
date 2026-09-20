"""CRUD de Tags (etiquetas personales) -- Ronda 2 del hito de Drive avanzado.

Cubre: crear/listar/renombrar/borrar, el conflicto de nombre duplicado
(constraint único `(owner_id, name)`) y el aislamiento entre usuarios (las
etiquetas son personales, `GET /tags` nunca debe filtrar las de otro
usuario -- no hay vista cross-usuario ni siquiera para admin, ver
app/tags/router.py)."""
from conftest import auth_headers, login_user, register_user


def _register_and_login(client):
    creds = register_user(client)
    login_data = login_user(client, creds["email"], creds["password"]).json()["data"]
    return creds, login_data["access_token"]


def test_tag_lifecycle_create_list_rename_delete(client):
    _, token = _register_and_login(client)

    create_resp = client.post(
        "/tags", headers=auth_headers(token), json={"name": "Trabajo", "color": "#ff0000"}
    )
    assert create_resp.status_code == 201, create_resp.text
    tag = create_resp.json()
    assert tag["name"] == "Trabajo"
    assert tag["color"] == "#ff0000"
    assert "id" in tag

    list_resp = client.get("/tags", headers=auth_headers(token))
    assert list_resp.status_code == 200
    assert [t["id"] for t in list_resp.json()] == [tag["id"]]

    rename_resp = client.patch(
        f"/tags/{tag['id']}", headers=auth_headers(token), json={"name": "Personal", "color": "#00ff00"}
    )
    assert rename_resp.status_code == 200, rename_resp.text
    assert rename_resp.json()["name"] == "Personal"
    assert rename_resp.json()["color"] == "#00ff00"

    delete_resp = client.delete(f"/tags/{tag['id']}", headers=auth_headers(token))
    assert delete_resp.status_code == 204

    list_after_delete = client.get("/tags", headers=auth_headers(token))
    assert list_after_delete.json() == []


def test_duplicate_tag_name_for_same_user_is_rejected(client):
    _, token = _register_and_login(client)

    first = client.post("/tags", headers=auth_headers(token), json={"name": "Facturas"})
    assert first.status_code == 201, first.text

    duplicate = client.post("/tags", headers=auth_headers(token), json={"name": "Facturas"})
    assert duplicate.status_code in (400, 409), duplicate.text
    assert duplicate.json().get("detail")  # mensaje claro, no un 500 crudo


def test_renaming_tag_to_an_existing_name_is_also_rejected(client):
    """El chequeo de nombre duplicado también corre en PATCH, no solo en
    creación -- renombrar una etiqueta al nombre de otra ya existente del
    mismo usuario debe fallar igual (mismo constraint único de fondo)."""
    _, token = _register_and_login(client)

    tag_a = client.post("/tags", headers=auth_headers(token), json={"name": "Uno"}).json()
    tag_b = client.post("/tags", headers=auth_headers(token), json={"name": "Dos"}).json()

    resp = client.patch(f"/tags/{tag_b['id']}", headers=auth_headers(token), json={"name": "Uno"})
    assert resp.status_code in (400, 409), resp.text

    # La etiqueta B no quedó renombrada a medias.
    listing = client.get("/tags", headers=auth_headers(token)).json()
    names = {t["id"]: t["name"] for t in listing}
    assert names[tag_a["id"]] == "Uno"
    assert names[tag_b["id"]] == "Dos"


def test_user_b_does_not_see_user_a_tags(client):
    _, token_a = _register_and_login(client)
    _, token_b = _register_and_login(client)

    create_resp = client.post("/tags", headers=auth_headers(token_a), json={"name": "SoloDeA"})
    assert create_resp.status_code == 201, create_resp.text

    listing_b = client.get("/tags", headers=auth_headers(token_b))
    assert listing_b.status_code == 200
    assert listing_b.json() == []

    listing_a = client.get("/tags", headers=auth_headers(token_a))
    assert len(listing_a.json()) == 1


def test_user_b_cannot_rename_or_delete_user_a_tag(client):
    """Ownership estricto en PATCH/DELETE -- ver `_get_owned_tag` en
    app/tags/router.py. 404 (no 403) para no filtrar si el id existe."""
    _, token_a = _register_and_login(client)
    _, token_b = _register_and_login(client)

    tag_a = client.post("/tags", headers=auth_headers(token_a), json={"name": "DeA"}).json()

    rename_attempt = client.patch(
        f"/tags/{tag_a['id']}", headers=auth_headers(token_b), json={"name": "Robada"}
    )
    assert rename_attempt.status_code == 404

    delete_attempt = client.delete(f"/tags/{tag_a['id']}", headers=auth_headers(token_b))
    assert delete_attempt.status_code == 404

    # La etiqueta de A sigue intacta.
    still_there = client.get("/tags", headers=auth_headers(token_a)).json()
    assert still_there[0]["name"] == "DeA"
