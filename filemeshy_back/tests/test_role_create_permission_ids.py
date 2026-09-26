"""Ronda 12 (B4) -- alta de rol atomica con `permission_ids`.

Bug: POST /roles aceptaba `permissions: Dict` (JSONB legacy sin lector) y NO
escribia en `role_permissions` -> un cliente API que mandaba `permissions`
creaba un rol con 0 permisos efectivos. Ahora `permission_ids` se persiste en
la misma transaccion del alta; ids inexistentes -> 422 sin dejar rol."""
import uuid

import pytest
from sqlalchemy import text

from conftest import PRIVILEGED_EMAILS, auth_headers, login_user, register_user


@pytest.fixture
def super_admin_token(client, db_session):
    import app.worker.celery_app  # noqa: F401  (registra todos los modelos ORM)

    from scripts.seed_permissions import seed

    seed()
    creds = register_user(client)
    role_id = db_session.execute(text("SELECT id FROM roles WHERE name = 'SUPER_ADMIN'")).scalar_one()
    db_session.execute(
        text("UPDATE users SET role_id = :r WHERE email = :e"), {"r": role_id, "e": creds["email"]}
    )
    db_session.commit()
    PRIVILEGED_EMAILS.append(creds["email"])  # se baja a USER y se desactiva al terminar el test
    from app.users.repository import user as crud_user
    from app.users.service import user_service

    user = crud_user.get_by_email(db_session, creds["email"])
    user_service.recalculate_permissions_for_user(db_session, user.id)
    db_session.commit()
    return login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]


@pytest.fixture
def role_cleanup(db_session):
    """Borra por SQL los roles PYTEST_* creados por el test (BD compartida)."""
    yield
    db_session.rollback()
    # `_` escapado: en LIKE es comodín de un carácter.
    db_session.execute(text(r"DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE name LIKE 'PYTEST\_%' ESCAPE '\')"))
    db_session.execute(text(r"DELETE FROM roles WHERE name LIKE 'PYTEST\_%' ESCAPE '\'"))
    db_session.commit()


def _role_name():
    return f"PYTEST_{uuid.uuid4().hex[:10].upper()}"


def _catalog_ids(client, token, n=2):
    role_id = client.get("/roles", headers=auth_headers(token)).json()
    role_id = (role_id if isinstance(role_id, list) else role_id.get("items", role_id))[0]["id"]
    catalog = client.get(f"/roles/{role_id}/permissions", headers=auth_headers(token)).json()["catalog"]
    assert len(catalog) >= n
    return [c["id"] for c in catalog[:n]]


def _assigned(client, token, role_id):
    return client.get(f"/roles/{role_id}/permissions", headers=auth_headers(token)).json()["assigned_permission_ids"]


def test_create_role_with_permission_ids_persists_exactly_those(client, super_admin_token, role_cleanup):
    ids = _catalog_ids(client, super_admin_token, 3)
    resp = client.post(
        "/roles",
        headers=auth_headers(super_admin_token),
        json={"name": _role_name(), "display_name": "Pytest rol", "permission_ids": ids},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["permissions_count"] == 3
    assert sorted(_assigned(client, super_admin_token, resp.json()["id"])) == sorted(ids)


def test_create_role_without_permission_ids_has_zero(client, super_admin_token, role_cleanup):
    resp = client.post(
        "/roles", headers=auth_headers(super_admin_token), json={"name": _role_name(), "display_name": "Pytest vacio"}
    )
    assert resp.status_code == 201, resp.text
    assert _assigned(client, super_admin_token, resp.json()["id"]) == []


def test_legacy_permissions_field_is_accepted_but_has_no_effect(client, super_admin_token, role_cleanup):
    resp = client.post(
        "/roles",
        headers=auth_headers(super_admin_token),
        json={"name": _role_name(), "display_name": "Pytest legacy", "permissions": {"files": ["view"]}},
    )
    assert resp.status_code == 201, resp.text
    assert _assigned(client, super_admin_token, resp.json()["id"]) == []


def test_create_role_with_unknown_permission_id_is_rejected_and_role_not_created(
    client, super_admin_token, db_session, role_cleanup
):
    good = _catalog_ids(client, super_admin_token, 1)[0]
    name = _role_name()
    resp = client.post(
        "/roles",
        headers=auth_headers(super_admin_token),
        json={"name": name, "display_name": "Pytest malo", "permission_ids": [good, str(uuid.uuid4())]},
    )
    assert 400 <= resp.status_code < 500, resp.text
    db_session.expire_all()
    assert db_session.execute(text("SELECT count(*) FROM roles WHERE name = :n"), {"n": name}).scalar_one() == 0


def test_create_role_duplicate_permission_ids_are_deduplicated(client, super_admin_token, role_cleanup):
    pid = _catalog_ids(client, super_admin_token, 1)[0]
    resp = client.post(
        "/roles",
        headers=auth_headers(super_admin_token),
        json={"name": _role_name(), "display_name": "Pytest dup", "permission_ids": [pid, pid]},
    )
    assert resp.status_code == 201, resp.text
    assert _assigned(client, super_admin_token, resp.json()["id"]) == [pid]


def test_create_role_forbidden_for_non_super_admin(client):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    resp = client.post(
        "/roles",
        headers=auth_headers(token),
        json={"name": _role_name(), "display_name": "No debe", "permission_ids": [str(uuid.uuid4())]},
    )
    assert resp.status_code == 403


# ---- Fase 4: tope, permisos inactivos y carrera de nombre -------------------

def test_more_than_1000_permission_ids_is_422(client, super_admin_token, role_cleanup):
    ids = [str(uuid.uuid4()) for _ in range(1001)]
    resp = client.post(
        "/roles",
        headers=auth_headers(super_admin_token),
        json={"name": _role_name(), "display_name": "Pytest tope", "permission_ids": ids},
    )
    assert resp.status_code == 422, resp.text
    # Rechazo por el TOPE (validación del schema), no por ids inexistentes.
    errors = resp.json()["detail"]
    assert isinstance(errors, list) and errors[0]["loc"][-1] == "permission_ids"
    assert "too_long" in errors[0]["type"] or "at most" in errors[0]["msg"]


def test_unknown_ids_detail_is_truncated(client, super_admin_token, role_cleanup):
    ids = [str(uuid.uuid4()) for _ in range(50)]
    resp = client.post(
        "/roles",
        headers=auth_headers(super_admin_token),
        json={"name": _role_name(), "display_name": "Pytest trunc", "permission_ids": ids},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "y 30 más" in detail
    assert detail.count("-") < 50 * 4  # no vuelca los 50 ids


def test_inactive_permission_is_rejected_and_role_not_created(client, super_admin_token, db_session, role_cleanup):
    pid = _catalog_ids(client, super_admin_token, 1)[0]
    name = _role_name()
    db_session.execute(text("UPDATE permissions SET is_active = false WHERE id = :p"), {"p": pid})
    db_session.commit()
    try:
        resp = client.post(
            "/roles",
            headers=auth_headers(super_admin_token),
            json={"name": name, "display_name": "Pytest inactivo", "permission_ids": [pid]},
        )
        assert resp.status_code == 422, resp.text
        db_session.expire_all()
        assert db_session.execute(text("SELECT count(*) FROM roles WHERE name = :n"), {"n": name}).scalar_one() == 0
    finally:
        db_session.execute(text("UPDATE permissions SET is_active = true WHERE id = :p"), {"p": pid})
        db_session.commit()


def test_name_race_integrity_error_becomes_409(client, super_admin_token, db_session, role_cleanup, monkeypatch):
    """Simula la carrera: get_by_name dice 'no existe' pero el INSERT choca con
    el unique de roles.name -> 409 (antes: IntegrityError -> 500)."""
    import pytest
    from fastapi import HTTPException

    from app.access_control.repository import role as crud_role
    from app.access_control.schemas import RoleCreate

    name = _role_name()
    first = client.post("/roles", headers=auth_headers(super_admin_token), json={"name": name, "display_name": "Primero"})
    assert first.status_code == 201, first.text

    monkeypatch.setattr(crud_role, "get_by_name", lambda db, n: None)
    with pytest.raises(HTTPException) as exc:
        crud_role.create(db_session, RoleCreate(name=name, display_name="Segundo"))
    assert exc.value.status_code == 409
