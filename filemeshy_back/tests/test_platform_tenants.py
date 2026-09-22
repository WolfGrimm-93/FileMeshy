"""Tests del panel de administración de tenants (`/platform/*`, Ronda 8).

Auth exclusiva por header `X-Platform-Key` (ver app/platform/router.py::get_platform_admin)
-- NO el JWT/RBAC normal de la app, a propósito (un admin de un tenant cliente
nunca debe poder ver/crear otros tenants). Este router solo se monta cuando
`DEPLOYMENT_MODE=cloud` (ver app/main.py) -- el stack de dev de este proyecto
corre normalmente en `DEPLOYMENT_MODE=local`, así que este archivo entero se
salta (`pytestmark` de abajo) salvo que se corra explícitamente contra un
proceso levantado con `DEPLOYMENT_MODE=cloud` + `PLATFORM_API_KEY` seteado
(ver PROGRESO_backend_tenants_admin.md para el comando exacto usado para
verificar esto en vivo).

Provisionar un tenant real (`POST /platform/tenants`) es caro -- crea un
schema Postgres nuevo y corre las ~47 migraciones de negocio + siembra de
roles/permisos + super admin -- así que este archivo provisiona como máximo
2 tenants (uno reusado de sólo-lectura para varios tests, uno dedicado para
el test que lo desactiva), no uno por test.
"""
import uuid

import httpx
import pytest

from app.core.config import settings

pytestmark = pytest.mark.skipif(
    settings.DEPLOYMENT_MODE != "cloud" or not settings.PLATFORM_API_KEY,
    reason=(
        "Requiere DEPLOYMENT_MODE=cloud + PLATFORM_API_KEY -- no aplica al "
        "stack de dev normal (DEPLOYMENT_MODE=local), donde /platform ni se monta."
    ),
)

WRONG_KEY = "clave-de-plataforma-incorrecta"


def _headers(key: str | None) -> dict:
    return {} if key is None else {"X-Platform-Key": key}


def _valid_headers() -> dict:
    return _headers(settings.PLATFORM_API_KEY)


@pytest.fixture(autouse=True)
def _reset_platform_rate_limit_bucket():
    """Limpia, ANTES de CADA test de este archivo, el bucket de rate-limit de
    `get_platform_admin` para 127.0.0.1 -- la IP real que ve el backend
    cuando este suite le pega a su propio `localhost:8000` desde DENTRO del
    contenedor (mismo criterio que `_reset_own_rate_limit_bucket` en
    conftest.py para `/auth/register`: sin este reset, el orden de ejecución
    de los tests importaría, porque todos comparten la misma IP real)."""
    try:
        from app.core.cache import cache

        if cache.enabled and cache.client:
            for prefix in ("rl:", "rl_lock:", "rl_lockout_count:"):
                cache.client.delete(f"{prefix}platform_admin:ip:127.0.0.1")
    except Exception:
        pass
    yield


@pytest.fixture(scope="module")
def platform_client(api_base_url):
    """Cliente HTTP propio (no el `client` de conftest.py) con timeout más
    generoso -- el alta de un tenant real corre migraciones de negocio de
    punta a punta y puede tardar más que el timeout de 10s del cliente
    default."""
    with httpx.Client(base_url=api_base_url, timeout=60.0) as c:
        yield c


def _provisionar_tenant(platform_client) -> dict:
    suffix = uuid.uuid4().hex[:10]
    slug = f"pytest-{suffix}"
    schema_name = f"tenant_pytest_{suffix}"
    resp = platform_client.post(
        "/platform/tenants",
        headers=_valid_headers(),
        json={
            "slug": slug,
            "schema_name": schema_name,
            "company_name": "Pytest Tenant Ronda 8",
            "plan": "standard",
        },
    )
    assert resp.status_code == 201, f"No se pudo provisionar tenant de prueba: {resp.status_code} {resp.text}"
    data = resp.json()["data"]
    # Regresión: TenantCreateResponse no declaraba `admin_email` (Pydantic lo
    # descartaba en silencio pese a que provisionar_tenant() ya lo devolvía en
    # el dict) -- el modal de credenciales del panel de admin del frontend
    # quedaba con el email vacío. Confirma que el campo llega poblado.
    assert data.get("admin_email") == f"admin@{slug}.filemeshy", (
        f"admin_email ausente o inesperado en la respuesta de POST /platform/tenants: {data}"
    )
    return {"tenant_id": data["tenant_id"], "slug": slug, "schema_name": schema_name}


@pytest.fixture(scope="module")
def provisioned_tenant(platform_client):
    """Un tenant real, provisionado UNA sola vez para todo el módulo -- lo
    usan los tests de lectura y de PATCH de `plan` (nunca el que desactiva,
    ver `tenant_to_deactivate`, para no dejar ese endpoint bloqueado y romper
    el resto de los tests de este archivo)."""
    return _provisionar_tenant(platform_client)


@pytest.fixture(scope="module")
def tenant_to_deactivate(platform_client):
    """Tenant dedicado y exclusivo del test que lo desactiva (`is_active=False`)
    -- separado de `provisioned_tenant` a propósito, ver su docstring."""
    return _provisionar_tenant(platform_client)


# ============================================================
# Auth (los 4 endpoints, sin key / con key incorrecta)
# ============================================================

def test_endpoints_require_platform_key(platform_client):
    fake_id = str(uuid.uuid4())
    # Bodies bien formados a propósito (cumplen los patterns de
    # TenantCreateRequest/TenantUpdateRequest) -- lo único que tiene que fallar
    # acá es la autenticación, no la validación del body (evita depender de en
    # qué orden FastAPI resuelve dependencias de router vs. parseo del body).
    cases = [
        ("POST", "/platform/tenants", {"slug": "pytest-authcheck", "schema_name": "tenant_pytest_authcheck", "company_name": "X", "plan": "standard"}),
        ("GET", "/platform/tenants", None),
        ("GET", f"/platform/tenants/{fake_id}", None),
        ("PATCH", f"/platform/tenants/{fake_id}", {"is_active": True}),
    ]
    for method, path, json_body in cases:
        resp = platform_client.request(method, path, json=json_body)
        assert resp.status_code == 401, f"{method} {path} sin header: {resp.status_code} {resp.text}"

        resp = platform_client.request(method, path, json=json_body, headers=_headers(WRONG_KEY))
        assert resp.status_code == 401, f"{method} {path} con key incorrecta: {resp.status_code} {resp.text}"


# ============================================================
# Rate limiting
# ============================================================

def test_rate_limit_locks_after_threshold_with_wrong_key(platform_client):
    from app.platform.router import PLATFORM_RATE_LIMIT_MAX_ATTEMPTS

    statuses = []
    # Un par de intentos de margen por encima del umbral, para confirmar que
    # el bloqueo de verdad dispara (no solo "casi llega").
    for i in range(PLATFORM_RATE_LIMIT_MAX_ATTEMPTS + 3):
        resp = platform_client.get(
            "/platform/tenants", headers=_headers(f"{WRONG_KEY}-{i}")
        )
        statuses.append(resp.status_code)

    assert statuses[0] == 401, (
        f"El primer intento con key incorrecta debería fallar con 401, no {statuses[0]} "
        f"-- ¿bucket de rate-limit sucio de otro test? statuses={statuses}"
    )
    assert 429 in statuses, (
        f"No se alcanzó 429 tras {len(statuses)} intentos fallidos con key incorrecta "
        f"(umbral configurado: {PLATFORM_RATE_LIMIT_MAX_ATTEMPTS}). statuses={statuses}"
    )
    # Una vez bloqueado, el bloqueo aplica incluso a partir de ahí (429, no 401)
    assert statuses[-1] == 429, f"El último intento debería seguir bloqueado (429): {statuses}"


def test_rate_limit_does_not_penalize_correct_key(platform_client):
    """Usar la key CORRECTA repetidas veces nunca debe sumar al contador de
    intentos fallidos -- confirma que el 429 de arriba es por intentos
    fallidos, no por volumen de requests en general."""
    for _ in range(5):
        resp = platform_client.get("/platform/tenants", headers=_valid_headers())
        assert resp.status_code == 200, resp.text


# ============================================================
# PATCH /platform/tenants/{tenant_id}
# ============================================================

def test_patch_plan_persists_and_reflects_on_next_get(platform_client, provisioned_tenant):
    tenant_id = provisioned_tenant["tenant_id"]

    resp = platform_client.patch(
        f"/platform/tenants/{tenant_id}",
        headers=_valid_headers(),
        json={"plan": "enterprise"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["plan"] == "enterprise"

    resp = platform_client.get(f"/platform/tenants/{tenant_id}", headers=_valid_headers())
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["plan"] == "enterprise"


def test_patch_empty_body_returns_400(platform_client, provisioned_tenant):
    resp = platform_client.patch(
        f"/platform/tenants/{provisioned_tenant['tenant_id']}",
        headers=_valid_headers(),
        json={},
    )
    assert resp.status_code == 400, resp.text


def test_patch_nonexistent_tenant_returns_404(platform_client):
    resp = platform_client.patch(
        f"/platform/tenants/{uuid.uuid4()}",
        headers=_valid_headers(),
        json={"is_active": True},
    )
    assert resp.status_code == 404, resp.text


def test_malformed_tenant_id_returns_422_not_500(platform_client):
    """Regresión de revisión adversarial: `tenant_id` tipado como `UUID` (no
    `str`) en el path -- un valor no-UUID tiene que rechazarse con 422 de
    Pydantic/FastAPI ANTES de tocar la DB, nunca llegar a un DataError de
    Postgres (500 genérico)."""
    resp = platform_client.get("/platform/tenants/no-es-un-uuid", headers=_valid_headers())
    assert resp.status_code == 422, resp.text

    resp = platform_client.patch(
        "/platform/tenants/no-es-un-uuid",
        headers=_valid_headers(),
        json={"is_active": True},
    )
    assert resp.status_code == 422, resp.text


def test_patch_is_active_false_blocks_tenant_via_middleware(platform_client, tenant_to_deactivate):
    """El hallazgo central de este endpoint: `is_active=False` no solo tiene
    que cambiar la fila, tiene que bloquear de verdad al tenant en el
    `TenantMiddleware` real (403 "Tenant inactivo"), la misma protección que
    ya usa un tenant provisionado a medias (ver tenants/service.py)."""
    tenant_id = tenant_to_deactivate["tenant_id"]
    slug = tenant_to_deactivate["slug"]

    # Sanity antes de desactivar: una request de negocio contra este tenant
    # (cualquier endpoint público de /auth alcanza -- el TenantMiddleware
    # corre ANTES de llegar al router, así que ni necesita datos sembrados)
    # NO debería ser 403 todavía.
    resp_before = platform_client.get(
        "/auth/turnstile-config", headers={"X-Tenant-Slug": slug}
    )
    assert resp_before.status_code != 403, (
        f"El tenant recién provisionado ya debería estar activo: {resp_before.status_code} {resp_before.text}"
    )

    resp = platform_client.patch(
        f"/platform/tenants/{tenant_id}",
        headers=_valid_headers(),
        json={"is_active": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["is_active"] is False

    resp_after = platform_client.get(
        "/auth/turnstile-config", headers={"X-Tenant-Slug": slug}
    )
    assert resp_after.status_code == 403, (
        f"El TenantMiddleware debería bloquear con 403 un tenant is_active=False, "
        f"pero devolvió {resp_after.status_code}: {resp_after.text}"
    )
    assert "inactivo" in resp_after.text.lower()
