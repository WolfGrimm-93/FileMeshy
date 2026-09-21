from fastapi import APIRouter

from app.platform.router import public_router
from app.auth.router import router as auth_router
from app.users.router import router as users_router, preferences_router as user_preferences_router
from app.audit.router import router as audit_router
from app.configuration.router import (
    admin_config_router,
    config_router,
    admin_configuration_router,
)
from app.access_control.router import roles_router, permissions_router
from app.notifications.router import router as notifications_router
from app.files.router import folders_router, files_router, shares_router, public_shares_router
from app.storage_quota.router import router as storage_quota_router
from app.tags.router import router as tags_router
from app.backups.router import router as backups_router
from app.shared.feature_flags import router as feature_flags_router

# Router principal V1 - prefijo /api/v1 se define aquí
api_router = APIRouter(prefix="/api/v1")

# Nota: platform_router (alta/config de tenants) NO se monta acá -- se monta
# aparte en app/main.py, condicionado a DEPLOYMENT_MODE == "cloud", igual que
# antes de la migración (ver RECON_RIESGOS.md, riesgo #7).

# Incluir routers de cada módulo (sin prefijo adicional, ya está en api_router)
api_router.include_router(public_router)  # Endpoints públicos (sin auth)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(audit_router)  # Auditoría (rutas /audit-logs/... hardcodeadas en el propio router)
api_router.include_router(config_router)
api_router.include_router(admin_config_router)  # Endpoints de configuración

# ========================================================================
# ROLES DINÁMICOS - Gestión de roles y permisos
# ========================================================================
api_router.include_router(roles_router, prefix="/roles", tags=["roles"])

# ========================================================================
# PREFERENCIAS DE USUARIO - Seguridad y Notificaciones
# ========================================================================
api_router.include_router(user_preferences_router)  # prefijo /user/preferences ya fijado en el router

# ========================================================================
# CONFIGURACIÓN ADMINISTRATIVA - Permisos y políticas de seguridad
# ========================================================================
api_router.include_router(admin_configuration_router)  # prefijo /admin/configuration ya fijado en el router

# Feature flags de módulos de negocio (extraído de admin_configuration.py):
# endpoints /modules, /modules/{module_key}, mismo prefijo que arriba para
# preservar la URL legacy /api/v1/admin/configuration/modules.
api_router.include_router(feature_flags_router, prefix="/admin/configuration", tags=["admin-configuration"])

# ========================================================================
# NOTIFICACIONES - Sistema de notificaciones del usuario
# ========================================================================
api_router.include_router(notifications_router, prefix="/notifications", tags=["notifications"])

# ========================================================================
# ARCHIVOS Y CARPETAS - Drive de FileMeshy
# ========================================================================
api_router.include_router(folders_router, prefix="/folders", tags=["folders"])
api_router.include_router(files_router, prefix="/files", tags=["files"])

# Compartir por link (Hito 2): revocación autenticada por id de share, y
# acceso público de solo lectura por token (sin Depends(get_current_user)).
api_router.include_router(shares_router, prefix="/shares", tags=["shares"])
api_router.include_router(public_shares_router, prefix="/public/shares", tags=["public-shares"])

# Etiquetas personales (Ronda 2): CRUD propio bajo /tags + los endpoints
# PUT /files/{id}/tags y PUT /folders/{id}/tags que cuelgan de files_router/
# folders_router de arriba (mismo motivo que los shares autenticados).
api_router.include_router(tags_router, prefix="/tags", tags=["tags"])

# Cuotas de almacenamiento por usuario (pantalla admin, Hito 3) -- prefijo
# /storage-quotas ya fijado en el propio router.
api_router.include_router(storage_quota_router)

api_router.include_router(permissions_router)  # Catálogo permisos canónicos

# Backups automáticos + verificación (Ronda 7) -- prefijo /admin/backups ya
# fijado en el propio router (mismo criterio que admin_configuration_router).
api_router.include_router(backups_router)
