"""Router del módulo de plataforma (alta y config de tenants en modo cloud).

Contiene DOS `APIRouter` separados (mismo patrón que
`access_control/router.py` -- `roles_router`/`permissions_router`), porque
tienen prefijos y modelos de auth distintos:

- `public_router` (prefix `/public`): endpoints sin autenticación, para la
  carga inicial de la app (branding, health check). Se monta como cualquier
  otro router en `api/v1/router.py`.
- `platform_router` (prefix `/platform`, protegido por `get_platform_admin`,
  header X-Platform-Key): alta y configuración de tenants. A diferencia de
  los otros 9 módulos, NO se incluye en `api/v1/router.py` -- se monta aparte
  en `app/main.py`, condicionado a `DEPLOYMENT_MODE == "cloud"` (ver
  RECON_RIESGOS.md, riesgo #7 -- decisión de dónde vive ese `if` queda para
  el Implementador 3).

Exentos de TenantMiddleware (administran la tabla `tenants` en sí, viven en
`public`, no en el schema de ningún tenant).
"""
import secrets
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.configuration import service as configuration_service
from app.tenants.service import (
    provisionar_tenant,
    ProvisioningError,
    list_tenants,
    get_tenant_by_id,
    actualizar_tenant,
)
from app.shared.schemas.common import SuccessResponse
from app.platform.schemas import (
    TenantCreateRequest,
    TenantCreateResponse,
    TenantListItem,
    TenantUpdateRequest,
)
# Reusa el rate limiter real (Redis con fallback en memoria) ya usado por
# /auth/login y /auth/register -- no reimplementar rate limiting desde cero.
from app.auth.service import RateLimiter, too_many_requests
# Reusa la resolución de IP confiable (Ronda 1: no confía en headers
# spoofeables como X-Real-IP/CF-Connecting-IP salvo que la conexión TCP real
# venga de settings.TRUSTED_PROXY_IPS) -- mismo motivo que /auth, un secreto
# de alto privilegio como X-Platform-Key no puede rate-limitearse por un
# header que cualquier cliente controla.
from app.auth.router import _get_real_ip

# ===== PLATAFORMA (Fase 3 -- alta y config de tenants) =====
# Credencial separada del login de tenant: un usuario de una empresa NUNCA
# debe poder crear ni ver otros tenants. Solo tiene sentido en modo cloud --
# el router de /api/v1/platform ni se registra fuera de ese modo (ver main.py).
platform_key_header = APIKeyHeader(name="X-Platform-Key", auto_error=False)

# Umbral propio para X-Platform-Key, más estricto que el rate limit de login
# de usuario normal (settings.RATE_LIMIT_MAX_ATTEMPTS=5/15min) -- esta
# credencial da acceso de alta/baja de TODOS los tenants, un secreto de
# privilegio más alto que una contraseña individual. 10 intentos fallidos
# cada 15 minutos por IP: generoso para un operador que se equivoca tipeando
# la key, pero corta rápido un intento de fuerza bruta.
PLATFORM_RATE_LIMIT_MAX_ATTEMPTS = 10
PLATFORM_RATE_LIMIT_LOCK_DURATION = 900  # 15 minutos en segundos


def get_platform_admin(request: Request, api_key: Optional[str] = Depends(platform_key_header)) -> None:
    """Verifica el header X-Platform-Key contra PLATFORM_API_KEY (comparación
    en tiempo constante -- es un secreto, no un valor cualquiera).

    Rate limit por IP ANTES de comparar la key -- así un lockout ya activo
    devuelve 429 sin ni siquiera evaluar `compare_digest` de nuevo. Solo
    cuenta como intento (RateLimiter.record_attempt) el caso de key ausente o
    incorrecta -- una key correcta usada muchas veces (uso legítimo repetido
    del panel) nunca sube el contador, y además limpia cualquier resto de
    intentos fallidos previos (mismo criterio que /auth/login en un login
    exitoso: no dejar un cupo casi agotado colgando después de que quedó
    demostrado que quien pega es el operador real)."""
    ip_address = _get_real_ip(request)
    rl_key = f"platform_admin:ip:{ip_address}"

    is_allowed, rl_message = RateLimiter.check_rate_limit(
        rl_key,
        max_attempts=PLATFORM_RATE_LIMIT_MAX_ATTEMPTS,
        lock_duration=PLATFORM_RATE_LIMIT_LOCK_DURATION,
    )
    if not is_allowed:
        raise too_many_requests(rl_message)

    if not settings.PLATFORM_API_KEY or not api_key or not secrets.compare_digest(api_key, settings.PLATFORM_API_KEY):
        # window_seconds = mismo valor que lock_duration -- el contador de
        # intentos fallidos decae en la misma ventana de 15 minutos en la que
        # se cuentan ("10 intentos fallidos / 15 minutos", no un contador que
        # sobreviva una hora entera como el default genérico de RateLimiter).
        RateLimiter.record_attempt(rl_key, window_seconds=PLATFORM_RATE_LIMIT_LOCK_DURATION)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credencial de plataforma inválida",
        )

    RateLimiter.clear(rl_key)


# ========================================================================
# public_router -- endpoints públicos (sin autenticación requerida)
# Migrado de app/api/v1/endpoints/public.py.
# ========================================================================

public_router = APIRouter(prefix="/public", tags=["public"])


@public_router.get("/config", response_model=SuccessResponse)
async def get_public_config(db: Session = Depends(get_db)):
    """
    Obtener configuración pública para la carga inicial de la app

    Devuelve:
    - Branding de FileMeshy (estático -- ya no hay CompanySettings/multi-empresa,
      ver notas de configuration/models.py)
    - Información del dueño del sistema (SystemConfiguration)
    - Configuración de la app
    - Features habilitadas (SystemConfiguration)

    Se llama UNA SOLA VEZ al iniciar la app (ANTES de login)
    """
    # 1. Obtener información del dueño del sistema desde SystemConfiguration
    owner_name = configuration_service.get_system_config(db, "owner_name")
    owner_email = configuration_service.get_system_config(db, "owner_email")
    owner_phone = configuration_service.get_system_config(db, "owner_phone")

    owner_info = {
        "name": owner_name.value_string if owner_name else None,
        "email": owner_email.value_string if owner_email else None,
        "phone": owner_phone.value_string if owner_phone else None
    }

    # 2. Obtener features desde SystemConfiguration
    two_factor_enabled = configuration_service.get_system_config(db, "two_factor_auth_enabled")
    password_reset_enabled = configuration_service.get_system_config(db, "password_reset_enabled")
    user_registration_enabled = configuration_service.get_system_config(db, "user_registration_enabled")

    # 3. Armar respuesta
    config_data = {
        "company": {
            "business_name": "FileMeshy",
            "legal_name": "FileMeshy",
            "logo_path": None,
            "logo_icon_path": None,
            "primary_color": "#3A64D9",
            "secondary_color": "#6552E0",
            "phone": None,
            "email": None,
            "address": None,
            "website": None,
            "city": None,
            "province": None,
            "facebook": None,
            "instagram": None,
            "twitter": None,
            "whatsapp_business": None
        },
        "owner": owner_info,
        "app": {
            "version": settings.PROJECT_VERSION,
            "name": settings.PROJECT_NAME,
            "environment": "development" if settings.DEBUG else "production"
        },
        "features": {
            "two_factor_auth": two_factor_enabled.value_boolean if two_factor_enabled else False,
            "password_reset": password_reset_enabled.value_boolean if password_reset_enabled else True,
            "user_registration": user_registration_enabled.value_boolean if user_registration_enabled else False,
        },
    }

    return SuccessResponse(
        status=200,
        message="Configuración pública obtenida exitosamente",
        data=config_data
    )


@public_router.get("/health", response_model=SuccessResponse)
async def health_check():
    """
    Health check público

    Verifica que la API esté funcionando correctamente
    """
    return SuccessResponse(
        status=200,
        message="API funcionando correctamente",
        data={
            "status": "healthy",
            "service": "FileMeshy API"
        }
    )


# ========================================================================
# platform_router -- alta y config de tenants (Fase 3, modo cloud)
# Migrado de app/api/v1/endpoints/platform.py.
# ========================================================================

platform_router = APIRouter(prefix="/platform", tags=["platform"], dependencies=[Depends(get_platform_admin)])


@platform_router.post("/tenants", response_model=SuccessResponse, status_code=status.HTTP_201_CREATED)
def crear_tenant(payload: TenantCreateRequest):
    """Alta de un tenant nuevo: crea el schema y corre las 47 migraciones de negocio.

    Llamada síncrona (bloquea mientras corren las migraciones, unos segundos) --
    aceptable para el volumen actual (altas manuales, no un flujo de self-service
    de alto tráfico). Si eso cambia, mover a un job en background es la mejora natural.
    """
    try:
        resultado = provisionar_tenant(
            slug=payload.slug,
            schema_name=payload.schema_name,
            company_name=payload.company_name,
            plan=payload.plan,
        )
    except ProvisioningError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SuccessResponse(
        status=201,
        message="Tenant provisionado y activo",
        data=TenantCreateResponse(**resultado).model_dump(mode="json"),
    )


@platform_router.get("/tenants", response_model=SuccessResponse)
def listar_tenants(db: Session = Depends(get_db)):
    """Lista los tenants registrados -- lo mínimo para confirmar que un alta funcionó,
    no un panel de gestión (fuera de alcance por ahora, ver Obsidian)."""
    tenants = list_tenants(db)
    data = [TenantListItem.model_validate(t).model_dump(mode="json") for t in tenants]
    return SuccessResponse(status=200, message=f"{len(data)} tenants", data=data)


@platform_router.get("/tenants/{tenant_id}", response_model=SuccessResponse)
def ver_tenant(tenant_id: UUID, db: Session = Depends(get_db)):
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant no encontrado")
    return SuccessResponse(
        status=200,
        message="Tenant encontrado",
        data=TenantListItem.model_validate(tenant).model_dump(mode="json"),
    )


@platform_router.patch("/tenants/{tenant_id}", response_model=SuccessResponse)
def actualizar_tenant_endpoint(tenant_id: UUID, payload: TenantUpdateRequest, db: Session = Depends(get_db)):
    """Activa/desactiva un tenant o le cambia el plan -- único endpoint de
    escritura del panel de administración además del alta (`POST /tenants`).

    400 explícito (no la validación automática de Pydantic, ver el docstring
    de TenantUpdateRequest) si el body no trae ningún campo -- un PATCH que no
    cambia nada es un error de uso, no algo que valga la pena aceptar en
    silencio.

    `tenant_id: UUID` (no `str`) -- mismo criterio que el resto del codebase
    (access_control, tags, notifications, storage_quota, users): un valor no-UUID
    en el path se rechaza con 422 automático de FastAPI/Pydantic ANTES de tocar
    la DB. Sin esto, `actualizar_tenant`/`get_tenant_by_id` reciben el string
    crudo y Postgres lo rechaza con `DataError` -- 500 genérico en vez de un
    error limpio (hallazgo de revisión adversarial, reproducido en vivo)."""
    if not payload.tiene_algun_campo():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El PATCH debe incluir al menos uno de: is_active, plan.",
        )

    tenant = actualizar_tenant(db, tenant_id, is_active=payload.is_active, plan=payload.plan)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant no encontrado")

    return SuccessResponse(
        status=200,
        message="Tenant actualizado",
        data=TenantListItem.model_validate(tenant).model_dump(mode="json"),
    )


