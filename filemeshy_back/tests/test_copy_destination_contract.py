"""Ronda 12b -- contrato del destino de POST /files/{id}/copy y /folders/{id}/copy.

  * sin `folder_id` ni `to_root` (body ausente o `{}`) -> MISMA carpeta del original
  * `folder_id: <uuid>` -> esa carpeta
  * `to_root: true` o `folder_id: null` explícito -> raíz
  * `to_root: true` + `folder_id` no nulo -> 422
El caso "copiar un archivo que está dentro de una carpeta y que la copia caiga en
la raíz" salía de que el cliente mandaba `folder_id: null` (indistinguible de
"no enviado" en un JSON armado con valores por defecto)."""
import io

from conftest import auth_headers, grant_permission, login_user, register_user


def _setup(client, db_session):
    creds = register_user(client)
    grant_permission(db_session, creds["email"], "folders.create")
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    h = auth_headers(token)
    src = client.post("/folders", headers=h, json={"name": "origen"}).json()["id"]
    dst = client.post("/folders", headers=h, json={"name": "destino"}).json()["id"]
    f = client.post("/files/upload", headers=h, data={"folder_id": src},
                    files={"file": ("a.txt", io.BytesIO(b"contenido"), "text/plain")})
    assert f.status_code == 201, f.text
    return h, src, dst, f.json()["id"]


def _copy(client, h, file_id, body=None):
    kwargs = {"headers": h}
    if body is not None:
        kwargs["json"] = body
    return client.post(f"/files/{file_id}/copy", **kwargs)


def test_file_copy_without_destination_stays_in_same_folder(client, db_session):
    h, src, _, fid = _setup(client, db_session)
    for body in (None, {}):
        r = _copy(client, h, fid, body)
        assert r.status_code == 201, r.text
        assert r.json()["folder_id"] == src


def test_file_copy_to_explicit_folder(client, db_session):
    h, _, dst, fid = _setup(client, db_session)
    r = _copy(client, h, fid, {"folder_id": dst})
    assert r.status_code == 201 and r.json()["folder_id"] == dst


def test_file_copy_to_root_explicit_forms(client, db_session):
    h, _, _, fid = _setup(client, db_session)
    for body in ({"to_root": True}, {"folder_id": None}):
        r = _copy(client, h, fid, body)
        assert r.status_code == 201, r.text
        assert r.json()["folder_id"] is None


def test_to_root_with_folder_id_is_contradictory_422(client, db_session):
    h, _, dst, fid = _setup(client, db_session)
    assert _copy(client, h, fid, {"to_root": True, "folder_id": dst}).status_code == 422


def test_folder_copy_without_destination_stays_under_same_parent(client, db_session):
    h, src, dst, _ = _setup(client, db_session)
    child = client.post("/folders", headers=h, json={"name": "hija", "parent_id": src}).json()
    r = client.post(f"/folders/{child['id']}/copy", headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["parent_id"] == src
    r2 = client.post(f"/folders/{child['id']}/copy", headers=h, json={"to_root": True})
    assert r2.status_code == 201 and r2.json()["parent_id"] is None
    r3 = client.post(f"/folders/{child['id']}/copy", headers=h, json={"folder_id": dst})
    assert r3.status_code == 201 and r3.json()["parent_id"] == dst


# ---- Ronda 12c (MEDIO-4): ciclos y destino ajeno -----------------------------

def _folder_count(db_session, email):
    from sqlalchemy import text

    return db_session.execute(
        text("SELECT count(*) FROM folders f JOIN users u ON u.id = f.owner_id WHERE u.email = :e"), {"e": email}
    ).scalar_one()


def _quota_used(db_session, email):
    from sqlalchemy import text

    db_session.expire_all()
    return db_session.execute(
        text("SELECT coalesce(max(q.bytes_used), 0) FROM user_storage_quotas q JOIN users u ON u.id = q.user_id "
             "WHERE u.email = :e"), {"e": email}
    ).scalar_one()


def _user_with_tree(client, db_session):
    creds = register_user(client)
    grant_permission(db_session, creds["email"], "folders.create")
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    h = auth_headers(token)
    a = client.post("/folders", headers=h, json={"name": "A"}).json()["id"]
    b = client.post("/folders", headers=h, json={"name": "B", "parent_id": a}).json()["id"]
    c = client.post("/folders", headers=h, json={"name": "C", "parent_id": b}).json()["id"]
    client.post("/files/upload", headers=h, data={"folder_id": a},
                files={"file": ("x.txt", io.BytesIO(b"contenido"), "text/plain")})
    return creds["email"], h, a, b, c


def test_copy_folder_into_itself_or_descendant_is_400_and_creates_nothing(client, db_session):
    email, h, a, b, c = _user_with_tree(client, db_session)
    folders_before, quota_before = _folder_count(db_session, email), _quota_used(db_session, email)
    for target in (a, b, c):  # ella misma, hija, nieta
        r = client.post(f"/folders/{a}/copy", headers=h, json={"folder_id": target})
        assert r.status_code == 400, (target, r.status_code, r.text)
        assert "subcarpetas" in r.json()["detail"] or "sí misma" in r.json()["detail"]
    assert _folder_count(db_session, email) == folders_before
    assert _quota_used(db_session, email) == quota_before


def test_copy_folder_into_non_descendant_still_works(client, db_session):
    email, h, a, b, c = _user_with_tree(client, db_session)
    other = client.post("/folders", headers=h, json={"name": "otra"}).json()["id"]
    r = client.post(f"/folders/{b}/copy", headers=h, json={"folder_id": other})
    assert r.status_code == 201 and r.json()["parent_id"] == other


def test_copy_to_foreign_destination_is_404(client, db_session):
    _, h, a, _, _ = _user_with_tree(client, db_session)
    _, h_other, a_other, _, _ = _user_with_tree(client, db_session)
    assert client.post(f"/folders/{a}/copy", headers=h, json={"folder_id": a_other}).status_code == 404
    f = client.post("/files/upload", headers=h, files={"file": ("y.txt", io.BytesIO(b"y"), "text/plain")}).json()
    assert client.post(f"/files/{f['id']}/copy", headers=h, json={"folder_id": a_other}).status_code == 404


def test_copy_respects_max_depth_with_explicit_destination(client, db_session):
    from app.files.router import MAX_FOLDER_DEPTH

    creds = register_user(client)
    grant_permission(db_session, creds["email"], "folders.create")
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    h = auth_headers(token)
    parent = None
    for i in range(MAX_FOLDER_DEPTH):
        body = {"name": f"n{i}"} if parent is None else {"name": f"n{i}", "parent_id": parent}
        r = client.post("/folders", headers=h, json=body)
        assert r.status_code == 201, (i, r.text)
        parent = r.json()["id"]
    leaf = parent
    src = client.post("/folders", headers=h, json={"name": "suelta"}).json()["id"]
    r = client.post(f"/folders/{src}/copy", headers=h, json={"folder_id": leaf})
    assert r.status_code == 400 and "Profundidad" in r.json()["detail"]
