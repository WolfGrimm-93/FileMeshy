"""Ronda 12b -- los `action_url` de las notificaciones tienen que ser rutas
REALES del frontend (antes: `/configuracion/almacenamiento` y
`/archivos/compartidos` -> 404). VALID_ROUTES sale de filemeshy_front/src/App.tsx
(rutas hijas de la app autenticada, con `/` inicial)."""
import ast
import io
import pathlib
import re

from sqlalchemy import text

from conftest import auth_headers, grant_permission, login_user, register_user

VALID_ROUTES = {
    "/dashboard", "/archivos", "/compartido-conmigo", "/usuarios", "/usuarios/nuevo", "/roles", "/roles/nuevo",
    "/permisos", "/preferencias", "/notificaciones", "/logs", "/cuotas-almacenamiento", "/configuracion",
    "/copias-seguridad",
}


def test_valid_routes_match_frontend_router_when_available():
    """Si el código del frontend está montado, VALID_ROUTES no puede quedar viejo
    (en el contenedor backend no está: se omite)."""
    app_tsx = pathlib.Path("/mnt/toji/Projects/FileMeshy/filemeshy_front/src/App.tsx")
    if not app_tsx.exists():
        return
    paths = set(re.findall(r"path:\s*'([a-z0-9\-/]+)'", app_tsx.read_text()))
    assert {p.lstrip("/") for p in VALID_ROUTES if "/:" not in p} <= paths


def test_every_action_url_literal_in_backend_source_is_a_valid_route():
    """Recorre el código de app/ y comprueba TODO `action_url=` con literal (y las
    constantes de app/notifications/routes.py)."""
    from app.notifications import routes

    for name in ("ACTION_URL_SHARED_WITH_ME", "ACTION_URL_MY_FILES", "ACTION_URL_AUDIT_LOGS", "ACTION_URL_PREFERENCES"):
        assert getattr(routes, name) in VALID_ROUTES, name
    # las URLs viejas ya no son válidas
    assert not (set(routes.LEGACY_ACTION_URL_MAP) & VALID_ROUTES)

    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    if not root.exists():  # corrida desde el tmpfs de tests
        root = pathlib.Path("/app/app")
    found = []
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "action_url":
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    found.append((py.name, node.value.value))
    assert found, "no se encontró ningún action_url literal: el escaneo no comprobó nada"
    for fname, url in found:
        assert url in VALID_ROUTES, f"{fname}: action_url inválida {url!r}"


def test_directed_share_notification_points_to_shared_with_me(client, db_session):
    creds_a = register_user(client)
    grant_permission(db_session, creds_a["email"], "shares.create")
    token_a = login_user(client, creds_a["email"], creds_a["password"]).json()["data"]["access_token"]
    creds_b = register_user(client)
    token_b = login_user(client, creds_b["email"], creds_b["password"]).json()["data"]["access_token"]
    f = client.post("/files/upload", headers=auth_headers(token_a),
                    files={"file": ("n.txt", io.BytesIO(b"x"), "text/plain")}).json()
    r = client.post(f"/files/{f['id']}/shares", headers=auth_headers(token_a),
                    json={"shared_with_email": creds_b["email"]})
    assert r.status_code == 201, r.text
    items = client.get("/notifications", headers=auth_headers(token_b)).json()["items"]
    urls = [n["action_url"] for n in items if n.get("action_url")]
    assert urls and all(u in VALID_ROUTES for u in urls), urls
    assert "/compartido-conmigo" in urls


def test_quota_warning_notification_uses_valid_route(client, db_session):
    import app.worker.celery_app  # noqa: F401

    from app.storage_quota.service import _notify_if_near_limit

    creds = register_user(client)
    uid = db_session.execute(text("SELECT id FROM users WHERE email = :e"), {"e": creds["email"]}).scalar_one()
    db_session.execute(
        text("INSERT INTO user_storage_quotas (id, user_id, limit_bytes, bytes_used) "
             "VALUES (gen_random_uuid(), :u, 1000, 950) ON CONFLICT (user_id) DO UPDATE SET limit_bytes=1000, bytes_used=950"),
        {"u": uid},
    )
    db_session.commit()
    _notify_if_near_limit(db_session, uid)
    urls = db_session.execute(
        text("SELECT action_url FROM notifications WHERE user_id = :u AND type = 'almacenamiento'"), {"u": uid}
    ).scalars().all()
    assert urls and all(u in VALID_ROUTES for u in urls), urls


def test_fix_notification_urls_script_is_idempotent(client, db_session):
    import app.worker.celery_app  # noqa: F401

    from scripts.fix_notification_urls import fix_notification_urls

    creds = register_user(client)
    uid = db_session.execute(text("SELECT id FROM users WHERE email = :e"), {"e": creds["email"]}).scalar_one()
    db_session.execute(
        text("INSERT INTO notifications (id, user_id, title, message, type, severity, action_url, is_read) "
             "VALUES (gen_random_uuid(), :u, 't', 'm', 'compartido', 'info', '/archivos/compartidos', false)"),
        {"u": uid},
    )
    db_session.commit()
    dry = fix_notification_urls(dry_run=True)
    assert dry["/archivos/compartidos"] >= 1
    assert db_session.execute(text("SELECT count(*) FROM notifications WHERE action_url='/archivos/compartidos' AND user_id=:u"), {"u": uid}).scalar_one() == 1
    fix_notification_urls(dry_run=False)
    db_session.expire_all()
    assert db_session.execute(text("SELECT action_url FROM notifications WHERE user_id=:u"), {"u": uid}).scalar_one() == "/compartido-conmigo"
    assert fix_notification_urls(dry_run=True) == {"/archivos/compartidos": 0, "/configuracion/almacenamiento": 0}


def test_fix_notification_urls_all_schemas_sums_per_schema(monkeypatch):
    import scripts.fix_notification_urls as mod

    calls = []

    def fake(*, dry_run, db=None, schema=None):
        calls.append((schema, dry_run))
        return {"/archivos/compartidos": 2, "/configuracion/almacenamiento": 1}

    monkeypatch.setattr(mod, "fix_notification_urls", fake)
    total = mod.fix_notification_urls_all_schemas(dry_run=True, schemas=["t_a", "t_b"])
    assert calls == [("t_a", True), ("t_b", True)]
    assert total == {"/archivos/compartidos": 4, "/configuracion/almacenamiento": 2}
