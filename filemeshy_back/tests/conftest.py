"""Fixtures compartidas del test suite de FileMeshy backend.

Corre DENTRO del contenedor backend
(`docker compose exec backend python -m pytest tests/ -v`) contra el stack
real ya levantado -- Postgres, Redis y MinIO reales, sin mocks. `httpx.Client`
apunta a `http://localhost:8000` (el propio proceso uvicorn del contenedor),
así se ejercitan también los middlewares (CORS, CSRF, audit, security
headers) tal cual los ve un cliente real, no solo el ASGI in-process de
`TestClient`.

Todos los datos que crean estos tests usan el prefijo `pytest_` en el email --
la Postgres de este stack es la MISMA que se usa para pruebas manuales, y
puede estar siendo usada en paralelo por otro test (funcional, por curl/httpx)
mientras corre este suite. Nunca asumir estado vacío ni tocar/borrar nada que
no lleve ese prefijo.
"""
from __future__ import annotations

import json
import random
import uuid

import httpx
import pytest

BASE_URL = "http://localhost:8000"
API_PREFIX = "/api/v1"

DEFAULT_PASSWORD = "Pytest123!"


# Fase 4 (Ronda 12): emails de usuarios pytest_* promovidos a ADMIN/SUPER_ADMIN
# por los helpers de tests. La fixture autouse `_demote_privileged_users` los
# baja a USER y los desactiva al terminar cada test, para que ninguna corrida
# deje cuentas privilegiadas con contraseña conocida en la BD del stack.
PRIVILEGED_EMAILS: list[str] = []


def unique_email() -> str:
    """Email único con prefijo pytest_ -- nunca colisiona entre corridas ni
    con datos de pruebas manuales.

    Dominio `example.com` (no `.test`/`.example`/`.invalid`): el paquete
    `email-validator` que usa `EmailStr` de Pydantic rechaza esos TLD como
    "special-use domain" aunque sean justamente los reservados por la RFC
    2606 para testing -- confirmado en vivo al armar este suite (register
    devolvía 422 con `.test`)."""
    return f"pytest_{uuid.uuid4().hex[:12]}@example.com"


def _fake_source_ip() -> str:
    """IP privada (10.x.x.x) fijada por test -- YA NO aísla nada por sí sola
    (ver `_reset_own_rate_limit_bucket` para eso), se mantiene únicamente
    para que la fixture `client` no ande sin este header por si algún test
    puntual quisiera pasarlo. Con el fix de `_get_real_ip`
    (app/auth/router.py + settings.TRUSTED_PROXY_IPS, vacío en este stack de
    test), X-Real-IP se IGNORA por completo salvo que venga de una IP en esa
    lista de confianza -- este mismo header ya no engaña a nadie, que es
    justamente lo que `test_auth_ip_spoofing_fixed.py` confirma.
    """
    return f"10.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"


@pytest.fixture(scope="session")
def api_base_url() -> str:
    return f"{BASE_URL}{API_PREFIX}"


def _clear_rate_limit_keys() -> None:
    """Borra los buckets de rate-limit que usan los tests para 127.0.0.1 (la IP real que
    ve el backend cuando estos tests le pegan a localhost:8000 desde su propio contenedor)."""
    try:
        from app.core.cache import cache

        if cache.enabled and cache.client:
            names = (
                "register:ip:127.0.0.1",
                "public_share:127.0.0.1",
                "password-reset:ip:127.0.0.1",
                "password-reset-verify:ip:127.0.0.1",
            )
            for prefix in ("rl:", "rl_lock:", "rl_lockout_count:", "rlfw:"):
                for name in names:
                    cache.client.delete(f"{prefix}{name}")
            # buckets por email / sesión falsa del reset (prefijos con comodín)
            for pattern in ("*password-reset:email:*", "*pr_fake_session:*"):
                for key in cache.client.scan_iter(match=pattern, count=200):
                    cache.client.delete(key)
    except Exception:
        # Best-effort -- si Redis no está disponible por algún motivo, los tests igual corren.
        pass


@pytest.fixture(autouse=True)
def _reset_own_rate_limit_bucket():
    """Limpia, ANTES DE CADA TEST, el bucket de rate-limit de `/auth/register`
    para 127.0.0.1 -- la IP real que ve el backend cuando estos tests le
    pegan a localhost:8000 desde DENTRO del mismo contenedor.

    Antes del fix de `_get_real_ip` (ver auth/router.py), cada test podía
    "declararse" con una IP distinta vía X-Real-IP y así aislar su propio
    cupo de 8 registros/hora -- eso dejó de funcionar a propósito (era
    exactamente el bug que este fix arregla: rotar ese header ya NO evade el
    límite). Como consecuencia, TODOS los registros de este proceso de test
    comparten ahora el mismo cupo real (127.0.0.1) -- si esta fixture
    limpiara una sola vez por sesión (como hacía antes) en vez de una vez
    por test, los ~15+ registros acumulados entre test_auth.py,
    test_files_idor.py y los tests nuevos superarían el límite de 8/hora a
    mitad de suite. Limpiar por test (function-scoped) mantiene cada test
    aislado sin reintroducir el bug.

    No toca ningún otro key de Redis -- el otro agente que corre pruebas
    funcionales por curl/httpx desde el HOST llega por el puerto mapeado
    (58101), así que el backend lo ve con una IP de la red docker distinta a
    127.0.0.1, sin overlap con esto."""
    _clear_rate_limit_keys()
    yield
    # Ronda 12c: también AL TERMINAR -- tests que agotan a propósito un bucket (shares
    # públicos, reset de contraseña) no pueden dejar bloqueados a los siguientes.
    _clear_rate_limit_keys()


@pytest.fixture(autouse=True)
def _demote_privileged_users():
    """Teardown: baja a rol USER y desactiva a los usuarios pytest_* que el
    test promovió (ver PRIVILEGED_EMAILS). Solo toca emails `pytest_...`."""
    yield
    if not PRIVILEGED_EMAILS:
        return
    emails = [e for e in PRIVILEGED_EMAILS if e.startswith("pytest_")]
    PRIVILEGED_EMAILS.clear()
    if not emails:
        return
    from sqlalchemy import text

    from app.core.database import SessionLocal

    session = SessionLocal()
    try:
        session.execute(
            text(
                "UPDATE users SET role_id = (SELECT id FROM roles WHERE name = 'USER'), "
                "is_active = false WHERE email = ANY(:emails)"
            ),
            {"emails": emails},
        )
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


@pytest.fixture
def client(api_base_url):
    """Cliente HTTP real, sin cookies persistentes -- todo vía
    `Authorization: Bearer`, así el CSRFMiddleware de doble-submit-cookie ni
    entra en juego (ver app/shared/middleware/csrf.py: sin la cookie
    `filemeshy_csrf_token` presente, deja pasar la request tal cual).
    Header `X-Real-IP` fijo por test, ver `_fake_source_ip` (ya no confiable
    por diseño -- ver ese docstring)."""
    with httpx.Client(
        base_url=api_base_url,
        timeout=10.0,
        headers={"X-Real-IP": _fake_source_ip()},
    ) as c:
        yield c


def register_user(
    client: httpx.Client,
    *,
    email: str | None = None,
    password: str = DEFAULT_PASSWORD,
    first_name: str = "Pytest",
    last_name: str = "User",
) -> dict:
    """Registra un usuario nuevo y devuelve sus datos + credenciales usadas."""
    email = email or unique_email()
    resp = client.post(
        "/auth/register",
        json={
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "password": password,
        },
    )
    assert resp.status_code == 201, f"No se pudo registrar {email}: {resp.status_code} {resp.text}"
    return {"email": email, "password": password, "user": resp.json()}


def _clear_session_cookies(client: httpx.Client) -> None:
    """`httpx.Client` guarda automáticamente las cookies Set-Cookie de la
    respuesta (mismo comportamiento que un browser/`requests.Session`) y las
    reenvía en requests futuros al mismo host -- confirmado en vivo: sin este
    limpiado, la cookie `filemeshy_csrf_token` que deja `/auth/login` viaja
    sola (sin el header `X-XSRF-TOKEN` a juego) en la siguiente request
    autenticada, y el CSRFMiddleware la rechaza con 403 aunque estemos
    autenticando todo por `Authorization: Bearer` (ver
    app/shared/middleware/csrf.py). Este suite se apoya 100% en Bearer, así
    que la cookie de sesión nunca debería sobrevivir más allá de la propia
    respuesta de login."""
    client.cookies.clear()


def login_user(client: httpx.Client, email: str, password: str) -> httpx.Response:
    """Hace login y devuelve la respuesta cruda -- puede venir con tokens
    completos o con `requires_2fa`/`pre_auth_token` si el usuario tiene 2FA.
    Limpia del cliente cualquier cookie de sesión que la respuesta haya
    dejado (ver `_clear_session_cookies`)."""
    resp = client.post("/auth/login", json={"email": email, "password": password})
    _clear_session_cookies(client)
    return resp


def verify_2fa_login(client: httpx.Client, pre_auth_token: str, code: str) -> httpx.Response:
    """Completa un login con 2FA. Misma limpieza de cookies que `login_user`
    -- este endpoint también deja `filemeshy_refresh_token`/`filemeshy_csrf_token`."""
    resp = client.post(
        "/auth/2fa/verify-login",
        json={"pre_auth_token": pre_auth_token, "code": code},
    )
    _clear_session_cookies(client)
    return resp


def auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def registered_user(client):
    """Un usuario nuevo ya registrado (sin loguear todavía)."""
    return register_user(client)


@pytest.fixture
def db_session():
    """Sesión directa a Postgres (dentro del contenedor, misma DATABASE_URL
    que usa la app real) para setup que no tiene endpoint HTTP dedicado --
    ver `grant_permission` más abajo."""
    from app.core.database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def grant_permission(db_session, email: str, permission_code: str) -> None:
    """Agrega `permission_code` a los permisos efectivos de un usuario,
    directo en BD -- bypass deliberado del flujo real (que pasa por
    `user_permission_overrides` y requiere un admin autenticado).

    Se usa en test_files_idor.py para el caso de DELETE: el rol USER por
    defecto NO incluye `files.delete` (ver
    app/core/permissions.py::ROLE_PERMISSIONS_CANONICAL) -- sin este ajuste,
    el intento de un usuario B de borrar el archivo de A se frena en el gate
    de RBAC (has_permission, 403) ANTES de llegar siquiera a comprobar de
    quién es el archivo, y el test no estaría verificando la protección de
    ownership (`_get_owned_file`) que es el hallazgo real de la auditoría,
    solo una restricción de rol que ya existía por otro motivo.

    NUNCA usar esto para confirmar que un permiso nuevo quedó bien
    conectado de punta a punta (código -> seed -> BD real) -- bypassea por
    completo `role_permissions`, así que un permiso agregado al dict de
    `app/core/permissions.py` pero nunca sembrado en la tabla real igual
    pasaría el test. Para eso, usar `make_real_admin()` (ver más abajo).
    """
    from sqlalchemy import text

    row = db_session.execute(
        text("SELECT permissions FROM users WHERE email = :email"), {"email": email}
    ).first()
    assert row is not None, f"Usuario {email} no encontrado para otorgar permiso"
    current = list(row[0] or [])
    if permission_code not in current:
        current.append(permission_code)
    db_session.execute(
        text("UPDATE users SET permissions = CAST(:perms AS JSON) WHERE email = :email"),
        {"perms": json.dumps(current), "email": email},
    )
    db_session.commit()


def make_real_admin(client: httpx.Client, db_session) -> tuple[dict, str]:
    """Crea un usuario y lo convierte en ADMIN por el camino REAL que recorre
    un admin de producción: `role_id` -> tabla `role_permissions` (poblada
    por `scripts/seed_permissions.py`, idempotente -- se corre acá mismo
    para no depender de que alguien lo haya corrido contra este stack de
    test) -> `User.permissions` recalculado desde esa tabla (mismo mecanismo
    que dispara `PUT /users/{id}` con `role_id` nuevo, ver
    `app/users/service.py::recalculate_permissions_for_user`).

    A diferencia de `grant_permission()` (bypass directo de la columna JSON
    `users.permissions`, sin tocar `role_id` ni `role_permissions`), este
    helper SÍ ejercita el pipeline completo -- es el único de los dos que
    hubiera atrapado el hallazgo CRÍTICO de la revisión adversarial de
    Ronda 7 (backups): `backups.view` se agregó a
    `ROLE_PERMISSIONS_CANONICAL['ADMIN']` en `app/core/permissions.py`, pero
    nadie había corrido el seed contra la tabla real -- un ADMIN de verdad
    recibía 403. Los tests que usaban `grant_permission()` para ese mismo
    endpoint pasaban igual, porque nunca pasan por `role_permissions`.

    Usar `make_real_admin()` (no `grant_permission()`) para cualquier test
    que exista específicamente para confirmar que un permiso nuevo quedó
    bien conectado de punta a punta (dict en código -> seed -> BD ->
    resolución en runtime); seguir usando `grant_permission()` para el caso
    de uso original (forzar un permiso puntual sobre un usuario para aislar
    otra lógica de negocio, ej. ownership, sin que importe cómo llegó ese
    permiso).

    Import de `app.worker.celery_app` (nunca usado directo acá) a propósito
    ANTES de la primera query ORM sobre `User` -- ese módulo dispara, a
    nivel de import, `_register_all_orm_models()` (ver su docstring: el
    fix centralizado del bug real de Ronda 6) que importa TODOS los modelos
    con relaciones ORM basadas en string (`User.sessions =
    relationship("Session", ...)`, ver app/users/models.py) antes de que
    `configure_mappers()` se dispare. Sin esto, correr ESTE helper solo
    (ej. `pytest tests/test_backups_endpoints.py::test_real_admin_role...`
    en un proceso de pytest fresco, sin que ningún otro test haya importado
    ya medio backend) revienta con `InvalidRequestError: ... failed to
    locate a name ('Session')` -- confirmado en vivo al aislar este test."""
    import app.worker.celery_app  # noqa: F401

    from scripts.seed_permissions import seed

    seed()

    creds = register_user(client)

    from sqlalchemy import text

    role_row = db_session.execute(text("SELECT id FROM roles WHERE name = 'ADMIN'")).first()
    assert role_row is not None, "scripts/seed_permissions.py debería haber creado el rol ADMIN"
    admin_role_id = role_row[0]

    db_session.execute(
        text("UPDATE users SET role_id = :role_id WHERE email = :email"),
        {"role_id": admin_role_id, "email": creds["email"]},
    )
    db_session.commit()
    PRIVILEGED_EMAILS.append(creds["email"])

    from app.users.repository import user as crud_user
    from app.users.service import user_service

    user = crud_user.get_by_email(db_session, creds["email"])
    user_service.recalculate_permissions_for_user(db_session, user.id)
    db_session.commit()

    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    return creds, token
