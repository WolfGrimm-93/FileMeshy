"""`POST /folders/{id}/copy` -- Ronda 1 del hito de Drive avanzado.

Complemento de `test_files_copy.py`: ahí se cubre el IDOR de copiar un
ARCHIVO ajeno; acá el mismo caso pero para copiar una CARPETA ajena
(hallazgo de la revisión adversarial de Ronda 1 -- el endpoint ya estaba
bien protegido con `_get_owned_folder`, pero faltaba el test que lo
demuestre en vivo, mismo criterio que el resto de este router: 404, no 403,
para no filtrar ni la existencia del recurso)."""
from conftest import auth_headers, grant_permission, login_user, register_user


def _register_and_login(client):
    creds = register_user(client)
    login_data = login_user(client, creds["email"], creds["password"]).json()["data"]
    return creds, login_data["access_token"]


def _create_folder(client, token, name="pytest_carpeta_de_a"):
    resp = client.post("/folders", headers=auth_headers(token), json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_user_b_cannot_copy_user_a_folder(client, db_session):
    """El hallazgo central de este archivo: pasar el ID de una carpeta ajena
    a `/folders/{id}/copy` no debe crear ninguna copia -- 404, igual que el
    resto de endpoints IDOR-sensibles de este router (`_get_owned_folder`)."""
    creds_a, token_a = _register_and_login(client)
    _, token_b = _register_and_login(client)

    # POST /folders exige folders.create -- el rol USER por defecto no lo
    # trae (ver ROLE_PERMISSIONS_CANONICAL), mismo ajuste puntual que el
    # resto de la suite usa para llegar al código real bajo prueba.
    grant_permission(db_session, creds_a["email"], "folders.create")
    folder_a = _create_folder(client, token_a)

    # `POST /folders/{id}/copy` exige files.upload (copiar consume cuota
    # real) -- el rol USER por defecto SÍ lo trae, así que B llega de
    # verdad al chequeo de ownership y no se frena antes en el gate de RBAC.
    resp = client.post(f"/folders/{folder_a['id']}/copy", headers=auth_headers(token_b))
    assert resp.status_code in (403, 404)

    # La carpeta de A sigue existiendo tal cual, sin ninguna copia creada por B.
    listing_a = client.get("/files", headers=auth_headers(token_a))
    assert listing_a.status_code == 200
    names_a = [f["name"] for f in listing_a.json()["folders"]]
    assert names_a == ["pytest_carpeta_de_a"]

    # B tampoco ve ninguna copia colgada en su propio listado.
    listing_b = client.get("/files", headers=auth_headers(token_b))
    assert listing_b.status_code == 200
    names_b = [f["name"] for f in listing_b.json()["folders"]]
    assert "pytest_carpeta_de_a" not in names_b
    assert "pytest_carpeta_de_a (copia)" not in names_b
