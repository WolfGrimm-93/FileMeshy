"""Feature flags de módulos de negocio activables/desactivables.

Extraído de app/api/deps.py (require_module) y de app/routers/admin_configuration.py
(MODULE_FLAGS + endpoints /modules, /modules/{module_key}) durante la migración
a monolito modular. `invalidate_module_flag_cache` sigue viviendo en
app/core/cache.py (no se movió, solo se importa desde acá).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Callable
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.cache import (
    cache,
    get_module_flag_cache_key,
    MODULE_FLAG_CACHE_TTL,
    invalidate_module_flag_cache,
    bump_config_version,
)
from app.auth.service import get_current_active_user
from app.users.models import User


def require_module(module_key: str) -> Callable:
    """
    Crea una dependencia que verifica que un módulo de negocio esté activado
    (flag booleano en system_configuration, ej: 'compras_enabled').

    Se usa como dependency a nivel de router completo (include_router) para
    módulos activables/desactivables (Compras, Servicios Externos,
    Fidelización, Soporte, POS). Devuelve 403 (no 404) para que el
    frontend distinga "módulo apagado" de "endpoint inexistente".

    El valor se cachea en Redis con TTL corto; se invalida de inmediato al
    actualizar el flag (ver app.core.cache.invalidate_module_flag_cache).
    Si el flag no existe en BD todavía (ambiente sin seed), el módulo se
    considera activado por defecto (fail-open, mismo criterio que el resto
    de features en app/api/v1/endpoints/public.py).
    """
    def module_checker(db: Session = Depends(get_db)) -> None:
        from app.configuration import service as configuration_service

        cache_key = get_module_flag_cache_key(module_key)
        enabled = cache.get(cache_key)

        if enabled is None:
            config = configuration_service.get_system_config(db, module_key)
            enabled = bool(config.value_boolean) if config and config.value_boolean is not None else True
            cache.set(cache_key, enabled, ttl=MODULE_FLAG_CACHE_TTL)

        if not enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"El módulo '{module_key}' está desactivado"
            )

    return module_checker


# ========================================================================
# MÓDULOS DE NEGOCIO ACTIVABLES/DESACTIVABLES (Iniciativa A)
# ========================================================================
# Extraído de app/routers/admin_configuration.py. Flags booleanos en
# system_configuration; el enforcement real (403) es require_module() arriba,
# aplicado como dependency de router en app/api/v1/router.py.

# Varios flags de módulos de negocio no relacionado (punto de venta, compras,
# fidelización, cuentas por cobrar/pagar) se quitaron junto con esos módulos.
# servicios_externos_enabled/soporte_enabled se quitaron junto con
# ExternalService/SupportTicket (legacy sin consumidor real, ver
# app/models/external_service.py y app/models/support_ticket.py, borrados).
# No queda ningún módulo activable/desactivable por ahora -- dict vacío a propósito,
# no borrado, para no tener que rearmar get_modules_status/update_module_status
# si se agrega un módulo nuevo con este mismo mecanismo más adelante.
MODULE_FLAGS: dict[str, dict[str, str]] = {}

router = APIRouter()


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Exige ADMIN/SUPER_ADMIN -- mismo criterio que el resto de configuration/."""
    if not current_user.role_obj or current_user.role_obj.name not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de administrador",
        )
    return current_user


@router.get("/modules")
async def get_modules_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Estado actual de los módulos de negocio activables/desactivables."""
    from app.configuration import service as configuration_service

    data = {}
    for key in MODULE_FLAGS:
        cfg = configuration_service.get_system_config(db, key)
        data[key] = bool(cfg.value_boolean) if cfg and cfg.value_boolean is not None else True
    return {"data": data}


@router.put("/modules/{module_key}")
async def update_module_status(
    module_key: str,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Activar/desactivar un módulo de negocio (Compras, Servicios Externos,
    Fidelización, Soporte, POS)."""
    from app.configuration import service as configuration_service

    meta = MODULE_FLAGS.get(module_key)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Módulo '{module_key}' no reconocido"
        )

    enabled = bool(data.get("enabled", True))
    cfg = configuration_service.get_system_config(db, module_key)
    if cfg:
        configuration_service.update_system_config(
            db, module_key, value_boolean=enabled, updated_by=current_user.email
        )
    else:
        configuration_service.create_system_config(
            db,
            config_key=module_key,
            config_name=meta["name"],
            config_category=meta["category"],
            data_type="boolean",
            value_boolean=enabled,
        )

    invalidate_module_flag_cache(module_key)
    bump_config_version()
    return {"ok": True, "module_key": module_key, "enabled": enabled}
