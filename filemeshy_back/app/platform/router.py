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

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.configuration import service as configuration_service
from app.tenants.service import provisionar_tenant, ProvisioningError, list_tenants, get_tenant_by_id
from app.shared.schemas.common import SuccessResponse
from app.platform.schemas import (
    TenantCreateRequest,
    TenantCreateResponse,
    TenantListItem,
)

# ===== PLATAFORMA (Fase 3 -- alta y config de tenants) =====
# Credencial separada del login de tenant: un usuario de una empresa NUNCA
# debe poder crear ni ver otros tenants. Solo tiene sentido en modo cloud --
# el router de /api/v1/platform ni se registra fuera de ese modo (ver main.py).
platform_key_header = APIKeyHeader(name="X-Platform-Key", auto_error=False)


def get_platform_admin(api_key: Optional[str] = Depends(platform_key_header)) -> None:
    """Verifica el header X-Platform-Key contra PLATFORM_API_KEY (comparación
    en tiempo constante -- es un secreto, no un valor cualquiera)."""
    if not settings.PLATFORM_API_KEY or not api_key or not secrets.compare_digest(api_key, settings.PLATFORM_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credencial de plataforma inválida",
        )


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
def ver_tenant(tenant_id: str, db: Session = Depends(get_db)):
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant no encontrado")
    return SuccessResponse(
        status=200,
        message="Tenant encontrado",
        data=TenantListItem.model_validate(tenant).model_dump(mode="json"),
    )


