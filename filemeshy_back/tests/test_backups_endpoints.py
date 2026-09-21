"""Ronda 7 -- endpoints admin de backups (`GET /admin/backups`,
`POST /admin/backups/run`), gateados por el permiso `backups.view`.

Mismo criterio de RBAC que el resto del proyecto: un usuario del rol por
defecto (sin el permiso) recibe 403 en ambos, y un usuario con el permiso
otorgado (vía `grant_permission`, bypass directo en BD del flujo real de
asignación de permisos -- mismo mecanismo que usan
test_files_idor.py/test_purge_file_versions_quota.py) puede listar y
disparar.

Además, `test_real_admin_role_can_list_and_trigger` ejercita el pipeline
COMPLETO (rol ADMIN asignado por `role_id` -> `scripts/seed_permissions.py`
-> tabla `role_permissions` real -> `User.permissions` recalculado) en vez
del atajo de `grant_permission()` -- ver `make_real_admin()` en
`conftest.py` para el porqué: es el único de los dos mecanismos que hubiera
atrapado el hallazgo CRÍTICO de la revisión adversarial (2026-09-21):
`backups.view` se agregó al dict de `app/core/permissions.py` pero nunca se
sembró contra la tabla real, así que un ADMIN real recibía 403 -- y los
tests con `grant_permission()` pasaban igual, porque ese helper nunca pasa
por `role_permissions`."""

from conftest import auth_headers, grant_permission, login_user, make_real_admin, register_user


def _register_login(client):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    return creds, token


def test_list_and_trigger_require_backups_permission(client):
    """Usuario normal (rol USER por defecto, sin `backups.view`) -- 403 en
    ambos endpoints."""
    _, token = _register_login(client)

    list_resp = client.get("/admin/backups", headers=auth_headers(token))
    assert list_resp.status_code == 403, list_resp.text

    run_resp = client.post("/admin/backups/run", headers=auth_headers(token))
    assert run_resp.status_code == 403, run_resp.text


def test_admin_with_permission_can_list_and_trigger(client, db_session):
    """Usuario con `backups.view` otorgado -- 200 al listar, 202 al
    disparar, y el listado refleja una corrida ya hecha (se fuerza una
    corrida síncrona de `backup_postgres` antes de listar, para no depender
    de que el `beat_schedule`/worker real ya haya corrido algo)."""
    creds, token = _register_login(client)
    grant_permission(db_session, creds["email"], "backups.view")

    from app.worker.tasks.backups import backup_postgres

    backup_postgres()

    list_resp = client.get("/admin/backups", headers=auth_headers(token))
    assert list_resp.status_code == 200, list_resp.text
    body = list_resp.json()
    assert body["total"] >= 1
    assert any(item["backup_type"] == "postgres" for item in body["items"])
    assert any(item["status"] == "success" for item in body["items"])

    filtered_resp = client.get(
        "/admin/backups", headers=auth_headers(token), params={"backup_type": "postgres"}
    )
    assert filtered_resp.status_code == 200, filtered_resp.text
    assert all(item["backup_type"] == "postgres" for item in filtered_resp.json()["items"])

    run_resp = client.post("/admin/backups/run", headers=auth_headers(token))
    assert run_resp.status_code == 202, run_resp.text
    assert run_resp.json()["queued"] is True


def test_real_admin_role_can_list_and_trigger(client, db_session):
    """Camino REAL de punta a punta -- rol ADMIN asignado vía `role_id`
    (nunca `grant_permission`), con `scripts/seed_permissions.py` corrido
    contra la BD de este stack de test (idempotente) para que
    `role_permissions` refleje `ROLE_PERMISSIONS_CANONICAL['ADMIN']` de
    `app/core/permissions.py` -- exactamente el pipeline que recorre un
    ADMIN de producción real, y el único capaz de agarrar una regresión
    donde un permiso nuevo se agrega al dict pero nunca se siembra en la
    tabla real (ver docstring del módulo y de `make_real_admin` en
    conftest.py)."""
    creds, token = make_real_admin(client, db_session)

    list_resp = client.get("/admin/backups", headers=auth_headers(token))
    assert list_resp.status_code == 200, (
        f"ADMIN real (rol asignado + seed corrido) debería poder listar backups: {list_resp.text}"
    )

    run_resp = client.post("/admin/backups/run", headers=auth_headers(token))
    assert run_resp.status_code == 202, (
        f"ADMIN real (rol asignado + seed corrido) debería poder disparar un backup: {run_resp.text}"
    )
    assert run_resp.json()["queued"] is True
