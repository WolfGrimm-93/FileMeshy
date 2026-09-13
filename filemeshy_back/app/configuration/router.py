"""Router del módulo de configuración.

Contiene TRES `APIRouter` separados (mismo patrón que `access_control/router.py`
-- `roles_router`/`permissions_router`), porque vienen de tres archivos reales
distintos con prefijos propios que no pueden fusionarse sin perder/duplicar
una URL:

- `admin_config_router` (prefix `/admin/config`): SMTP, config genérica,
  tipos de notificación, email -- migrado de app/api/v1/endpoints/admin_config.py.
- `config_router` (prefix `/config`): version, preferencias de usuario --
  migrado de app/api/v1/endpoints/configuration.py.
- `admin_configuration_router` (prefix `/admin/configuration`): políticas de
  seguridad, permisos, Turnstile -- migrado de app/routers/admin_configuration.py
  (SIN el bloque MODULE_FLAGS, que se extrajo a app/shared/feature_flags/).
"""
from typing import List
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.auth.service import get_current_active_user
from app.users.models import User
from app.core.cache import cache, get_config_version, invalidate_permissions_cache, bump_config_version

from app.configuration.schemas import (
    SecurityPoliciesResponse,
    SecurityPoliciesCreate,
    SecurityPoliciesUpdate,
    UserPreferencesUpdate,
)
from app.access_control.schemas import (
    PermissionResponse,
    PermissionCreate,
    PermissionUpdate,
    PermissionListResponse,
    PermissionBulkCreate,
)
from app.shared.schemas.common import SuccessResponse

from app.configuration.repository import (
    security_policies,
    crud_system_configuration,
    crud_user_preferences,
)
from app.access_control import service as access_control_service


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Exige ADMIN/SUPER_ADMIN -- mismo criterio en los 3 routers de este archivo."""
    if not current_user.role_obj or current_user.role_obj.name not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de administrador",
        )
    return current_user


# ========================================================================
# admin_config_router -- prefix /admin/config
# Migrado de app/api/v1/endpoints/admin_config.py.
# ========================================================================

admin_config_router = APIRouter(prefix="/admin/config", tags=["admin-config"])


# ===== SCHEMAS (locales al endpoint, igual que en el archivo original) =====

class SMTPConfigRequest(BaseModel):
    """Schema para configurar SMTP"""
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    email_from: str


class SMTPConfigResponse(BaseModel):
    """Schema para respuesta de configuración SMTP"""
    message: str
    data: dict


class SystemConfigResponse(BaseModel):
    """Schema para respuesta de configuraciones"""
    config_key: str
    config_name: str
    config_value: str | int | bool | dict


class SystemConfigCreateRequest(BaseModel):
    """Schema para crear configuración genérica"""
    config_key: str
    config_name: str
    config_category: str
    data_type: str  # string, number, boolean, json
    description: str = ""
    value_string: str | None = None
    value_number: float | None = None
    value_boolean: bool | None = None
    value_json: dict | None = None
    is_encrypted: bool = False
    is_readonly: bool = False


# ===== ENDPOINTS =====
# Los endpoints que servían los instaladores .exe/.msi de un producto de
# escritorio anterior (GET+upload+delete) se quitaron junto con el resto de
# ese negocio -- ver también platform/router.py (public_router).


@admin_config_router.get("/smtp", response_model=dict)
def get_smtp_config(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """
    Obtener configuración SMTP actual

    Solo administradores
    """
    from app.notifications.service import email_config_service

    config = email_config_service.get_smtp_config(db)

    # No retornar contraseña en GET
    if config.get('smtp_password'):
        config['smtp_password'] = '****'

    return {
        "message": "Configuración SMTP actual",
        "data": config,
        "is_configured": email_config_service.is_smtp_configured(db)
    }


@admin_config_router.post("/smtp", response_model=SMTPConfigResponse)
def update_smtp_config(
    request: SMTPConfigRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Actualizar configuración SMTP

    Solo administradores pueden hacer esto.
    La contraseña se encripta en la BD.
    """
    try:
        # Actualizar cada configuración
        configs_to_update = [
            ('SMTP_HOST', request.smtp_host, 'value_string'),
            ('SMTP_PORT', request.smtp_port, 'value_number'),
            ('SMTP_USER', request.smtp_user, 'value_string'),
            ('SMTP_PASSWORD', request.smtp_password, 'value_string'),
            ('EMAIL_FROM', request.email_from, 'value_string'),
        ]

        for config_key, value, value_type in configs_to_update:
            existing = crud_system_configuration.get_by_key(db, config_key)

            if existing:
                # Actualizar existente
                if value_type == 'value_string':
                    crud_system_configuration.update(
                        db,
                        config_key=config_key,
                        value_string=value,
                        updated_by=current_user.email
                    )
                elif value_type == 'value_number':
                    crud_system_configuration.update(
                        db,
                        config_key=config_key,
                        value_number=value,
                        updated_by=current_user.email
                    )
            else:
                # Crear nuevo (por si acaso no existe)
                if value_type == 'value_string':
                    crud_system_configuration.create(
                        db,
                        config_key=config_key,
                        config_name=config_key,
                        config_category='notifications',
                        data_type='string',
                        value_string=value,
                        is_encrypted=(config_key in ['SMTP_PASSWORD'])
                    )
                elif value_type == 'value_number':
                    crud_system_configuration.create(
                        db,
                        config_key=config_key,
                        config_name=config_key,
                        config_category='notifications',
                        data_type='number',
                        value_number=value,
                        is_encrypted=False
                    )

        return SMTPConfigResponse(
            message="Configuración SMTP actualizada exitosamente",
            data=request.model_dump(exclude={'smtp_password'}, by_alias=True)
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al actualizar configuración: {str(e)}"
        )


@admin_config_router.post("/smtp/test")
def test_smtp_config(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """
    Probar la configuración SMTP activa.
    Envía un email de prueba al destinatario configurado.
    """
    from app.notifications.service import EmailService
    from app.notifications.service import email_config_service as _email_cfg

    if not _email_cfg.is_smtp_configured(db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configuración SMTP incompleta"
        )
    smtp_cfg = _email_cfg.get_smtp_config(db)
    test_email = smtp_cfg.get('smtp_user')

    try:
        html_content = """
        <html><body style="font-family:Arial,sans-serif;padding:20px;">
          <h2 style="color:#3A64D9;">✅ Email de prueba — FileMeshy</h2>
          <p>La configuración de correo está funcionando correctamente.</p>
        </body></html>"""

        sent = EmailService._send_email(
            to_email=test_email,
            subject="Email de prueba — FileMeshy",
            html_content=html_content,
            db=db,
        )

        if sent:
            return {
                "message": "Email de prueba enviado correctamente vía SMTP",
                "status": "success",
                "provider": "smtp",
            }
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="El proveedor rechazó el email. Revisa los logs del servidor."
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al probar configuración de email: {str(e)}"
        )


@admin_config_router.get("/categories/{category}")
def get_config_by_category(
    category: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Obtener todas las configuraciones de una categoría

    Categorías disponibles:
    - notifications (email, SMTP)
    - appearance (tema, idioma)
    - security (contraseñas, 2FA)
    - billing (facturación)
    - etc.
    """
    configs = crud_system_configuration.get_by_category(db, category)

    if not configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No hay configuraciones en la categoría {category}"
        )

    return {
        "category": category,
        "data": [
            {
                "key": c.config_key,
                "name": c.config_name,
                "value": c.value_string or c.value_number or c.value_boolean or c.value_json,
                "is_encrypted": c.is_encrypted
            }
            for c in configs
        ]
    }


@admin_config_router.get("/all")
def get_all_configs(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """
    Obtener todas las configuraciones del sistema

    Las contraseñas y datos sensibles no se retornan.
    """
    configs = crud_system_configuration.get_all(db)

    result = []
    for c in configs:
        if c.is_encrypted:
            # No retornar datos encriptados
            value = "****"
        else:
            value = c.value_string or c.value_number or c.value_boolean or c.value_json

        result.append({
            "key": c.config_key,
            "name": c.config_name,
            "category": c.config_category,
            "value": value,
            "is_encrypted": c.is_encrypted,
            "version": c.version,
            "updated_at": c.updated_at
        })

    return {
        "total": len(result),
        "data": result
    }


@admin_config_router.post("/create")
def create_system_config(
    request: SystemConfigCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Crear una nueva configuración del sistema

    Endpoint genérico para crear cualquier tipo de configuración.
    Soporta string, number, boolean y json como tipos de datos.

    **Parámetros:**
    - config_key: Clave única (ej: email_smtp_host)
    - config_name: Nombre legible (ej: SMTP Host)
    - config_category: Categoría (ej: email, security, appearance)
    - data_type: Tipo de dato (string, number, boolean, json)
    - description: Descripción de la configuración
    - value_*: El valor según el tipo (value_string, value_number, etc)
    - is_encrypted: Si es dato sensible
    """
    try:
        # Verificar que no exista ya
        existing = crud_system_configuration.get_by_key(db, request.config_key)
        if existing:
            return {
                "message": f"Configuración '{request.config_key}' ya existe",
                "data": {
                    "key": existing.config_key,
                    "updated": False
                }
            }

        # Crear nueva configuración
        config = crud_system_configuration.create(
            db=db,
            config_key=request.config_key,
            config_name=request.config_name,
            config_category=request.config_category,
            data_type=request.data_type,
            value_string=request.value_string,
            value_number=request.value_number,
            value_boolean=request.value_boolean,
            value_json=request.value_json,
            description=request.description,
            is_encrypted=request.is_encrypted,
            is_readonly=request.is_readonly
        )

        return {
            "message": f"Configuración '{request.config_name}' creada exitosamente",
            "data": {
                "key": config.config_key,
                "name": config.config_name,
                "category": config.config_category,
                "created": True
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al crear configuración: {str(e)}"
        )


@admin_config_router.put("/update/{config_key}")
def update_system_config(
    config_key: str,
    request: SystemConfigCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Actualizar una configuración existente
    """
    try:
        config = crud_system_configuration.get_by_key(db, config_key)
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuración '{config_key}' no encontrada"
            )

        updated_config = crud_system_configuration.update(
            db=db,
            config_key=config_key,
            value_string=request.value_string,
            value_number=request.value_number,
            value_boolean=request.value_boolean,
            value_json=request.value_json,
            updated_by=current_user.email
        )

        return {
            "message": f"Configuración '{config_key}' actualizada",
            "data": {
                "key": updated_config.config_key,
                "updated": True
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al actualizar: {str(e)}"
        )


# ===== ENDPOINTS PARA FRONTEND (notification-types) =====

# Los tipos de negocio no relacionado (stock/pagos/ventas/compras/clientes) se
# podaron junto con sus tasks -- ver worker/tasks/notification_helpers.py::_DEFAULT_NOTIF_TYPES.
_DEFAULT_NOTIF_TYPES_CONFIG: dict = {}


@admin_config_router.get("/notification-types", response_model=dict)
def get_notification_types(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Obtener configuración de tipos de notificaciones (qué canales activa cada evento)."""
    config = crud_system_configuration.get_by_key(db, "notification_types")
    if config and config.value_json:
        return {"data": config.value_json}
    return {"data": _DEFAULT_NOTIF_TYPES_CONFIG}


class NotificationTypesUpdateRequest(BaseModel):
    types: dict  # { "stockBajo": { "email": true, "sistema": true }, ... }


@admin_config_router.put("/notification-types", response_model=dict)
def update_notification_types(
    request: NotificationTypesUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Guardar configuración de tipos de notificaciones."""
    config = crud_system_configuration.get_by_key(db, "notification_types")
    if config:
        crud_system_configuration.update(
            db, config_key="notification_types",
            value_json=request.types, updated_by=current_user.email,
        )
    else:
        crud_system_configuration.create(
            db,
            config_key="notification_types",
            config_name="Notification Types Config",
            config_category="notifications",
            data_type="json",
            value_json=request.types,
        )
    return {"message": "Tipos de notificaciones actualizados"}


# ===== ENDPOINTS PARA FRONTEND (email) =====

class EmailConfigResponse(BaseModel):
    """Schema para respuesta de configuración de email (Frontend-friendly)"""
    account_email: str | None = None
    account_username: str | None = None
    domain_name: str | None = None
    display_name: str | None = None
    imap_hostname: str | None = None
    imap_mail_hostname: str | None = None
    imap_insecure_port: int | None = None
    imap_secure_port: int | None = None
    service_type: str | None = None
    activesync_available: bool | None = None
    activesync_port: int | None = None
    support_plaintext_auth: str | None = None
    mail_archive: bool | None = None
    smtp_host: str | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None  # Será "****" cuando se obtenga
    smtp_insecure_port: int | None = None
    smtp_secure_port: int | None = None
    email_method: str | None = None  # 'smtp' (único proveedor soportado)


@admin_config_router.get("/email", response_model=dict)
def get_email_config(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """
    Obtener TODA la configuración de email (Frontend)

    Retorna todos los parámetros de email en un formato amigable para el frontend.
    Las contraseñas se retornan como '****' por seguridad.

    **Respuesta ejemplo:**
    ```json
    {
        "message": "Configuración de email",
        "data": {
            "account_email": "admin@example.com",
            "smtp_host": "smtp.example.com",
            "smtp_username": "admin@example.com",
            "smtp_password": "****",
            ...
        }
    }
    ```
    """
    configs = crud_system_configuration.get_by_category(db, "email")

    if not configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay configuración de email"
        )

    # Mapear a formato frontend-friendly
    data = {}
    for config in configs:
        # Convertir config_key "email_account_email" -> "account_email"
        # removeprefix solo quita el primer "email_", evitando doble reemplazo en "email_email_method"
        key = config.config_key.removeprefix("email_")

        # Obtener valor según tipo
        if config.is_encrypted and config.value_string:
            value = "****"  # Nunca se muestra en la respuesta, sea cual sea el valor real
        else:
            value = config.value_string or config.value_number or config.value_boolean or config.value_json
            # Los puertos se guardan como Numeric(12,2) — convertir a int
            if config.data_type == 'number' and value is not None:
                value = int(value)

        data[key] = value

    return {
        "message": "Configuración de email",
        "data": data
    }


class EmailConfigUpdateRequest(BaseModel):
    """Schema para actualizar configuración de email"""
    account_email: str | None = None
    account_username: str | None = None
    domain_name: str | None = None
    display_name: str | None = None
    imap_hostname: str | None = None
    imap_mail_hostname: str | None = None
    imap_insecure_port: int | None = None
    imap_secure_port: int | None = None
    service_type: str | None = None
    activesync_available: bool | None = None
    activesync_port: int | None = None
    support_plaintext_auth: str | None = None
    mail_archive: bool | None = None
    smtp_host: str | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_insecure_port: int | None = None
    smtp_secure_port: int | None = None
    email_method: str | None = None  # 'smtp' (único proveedor soportado)


@admin_config_router.put("/email", response_model=dict)
def update_email_config(
    request: EmailConfigUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Actualizar configuración de email (Frontend)

    Permite actualizar cualquier campo de email sin necesidad de reiniciar.
    La contraseña SMTP se encripta automáticamente antes de guardar.

    **Ejemplo de body:**
    ```json
    {
        "smtp_host": "nuevo.servidor.com",
        "smtp_port": 587,
        "smtp_password": "nueva_contraseña"
    }
    ```
    """
    try:
        from app.core.security import encrypt_sensitive_data

        # Mapeo inverso: account_email -> email_account_email
        updates = {}
        for key, value in request.model_dump(exclude_none=True).items():
            config_key = f"email_{key}"
            updates[config_key] = value

        updated_count = 0

        for config_key, value in updates.items():
            config = crud_system_configuration.get_by_key(db, config_key)

            if not config:
                # Crear la fila si no existe
                EMAIL_KEY_META = {
                    'email_smtp_host':          ('SMTP Host',             'email', 'string',  False),
                    'email_smtp_username':       ('SMTP Username',         'email', 'string',  False),
                    'email_smtp_password':       ('SMTP Password',         'email', 'string',  True),
                    'email_smtp_insecure_port':  ('SMTP Port (STARTTLS)',  'email', 'number',  False),
                    'email_smtp_secure_port':    ('SMTP Port (SSL)',       'email', 'number',  False),
                    'email_account_email':       ('Email Account',         'email', 'string',  False),
                    'email_account_username':    ('Account Username',      'email', 'string',  False),
                    'email_domain_name':         ('Domain Name',           'email', 'string',  False),
                    'email_display_name':        ('Display Name',          'email', 'string',  False),
                    'email_email_method':        ('Email Method',          'email', 'string',  False),
                }
                meta = EMAIL_KEY_META.get(config_key)
                if not meta:
                    continue
                config_name, category, data_type, is_encrypted = meta
                crud_system_configuration.create(
                    db=db,
                    config_key=config_key,
                    config_name=config_name,
                    config_category=category,
                    data_type=data_type,
                    is_encrypted=is_encrypted,
                )
                config = crud_system_configuration.get_by_key(db, config_key)
                if not config:
                    continue

            # Encriptar contraseña SMTP antes de guardar
            if config_key == 'email_smtp_password' and isinstance(value, str):
                value = encrypt_sensitive_data(value)

            # Actualizar según el tipo de dato
            if isinstance(value, str):
                crud_system_configuration.update(
                    db=db,
                    config_key=config_key,
                    value_string=value,
                    updated_by=current_user.email
                )
            elif isinstance(value, (int, float)):
                crud_system_configuration.update(
                    db=db,
                    config_key=config_key,
                    value_number=value,
                    updated_by=current_user.email
                )
            elif isinstance(value, bool):
                crud_system_configuration.update(
                    db=db,
                    config_key=config_key,
                    value_boolean=value,
                    updated_by=current_user.email
                )

            updated_count += 1

        return {
            "message": f"Configuración de email actualizada ({updated_count} campos)",
            "data": {
                "updated": True,
                "count": updated_count
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al actualizar: {str(e)}"
        )


# ========================================================================
# config_router -- prefix /config
# Migrado de app/api/v1/endpoints/configuration.py.
# ========================================================================

config_router = APIRouter(prefix="/config", tags=["configuration"])

# NOTA: este archivo tenía además /system-config/*, /company/* y /payment-methods/*
# y /summary/all -- se borraron (2026-09-03) por no tener ningún caller real
# (grep exhaustivo en filemeshy_front/filemeshy_mobile, confirmado por dos
# rondas de revisión adversarial). /company/* duplicaba lo que ya existía en
# app/routers/admin_configuration.py (también borrado ahí por la misma razón).
# El branding público (logo, colores) sigue sirviéndose vía GET /public/config
# (platform/router.py, public_router), que no depende de este router.


@config_router.get("/version")
async def get_config_version_endpoint(
    current_user: User = Depends(get_current_active_user),
):
    """
    R5: version global de configuracion, para polling multi-terminal.

    El frontend hace polling barato de este endpoint (una lectura de Redis, sin
    tocar la BD) para detectar cambios de config hechos desde OTRA terminal --
    el aviso de la MISMA terminal (localStorage + evento `storage`) no llega
    entre computadoras distintas.
    """
    return {"version": get_config_version()}


# ================ USER PREFERENCES ENDPOINTS ================
@config_router.get("/preferences/my-preferences")
async def get_my_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current user's preferences.

    🚀 Optimized with Redis cache (TTL 300s) - User-specific.
    """
    cache_key = f"config:preferences:user:{current_user.id}"

    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data

    preferences = crud_user_preferences.get_or_create(db, str(current_user.id))

    pref_data = {
        "id": preferences.id,
        "user_id": preferences.user_id,
        "theme": preferences.theme,
        "language": preferences.language,
        "font_size": preferences.font_size,
        "date_format": preferences.date_format,
        "time_format": preferences.time_format,
        "currency": preferences.currency,
        "dashboard_layout": preferences.dashboard_layout,
        "email_notifications": preferences.email_notifications,
        "system_notifications": preferences.system_notifications,
        "rows_per_page": preferences.rows_per_page,
        "created_at": preferences.created_at.isoformat() + 'Z' if preferences.created_at else None,
        "updated_at": preferences.updated_at.isoformat() + 'Z' if preferences.updated_at else None,
    }

    cache.set(cache_key, pref_data, ttl=300)
    return pref_data


@config_router.put("/preferences/my-preferences", response_model=SuccessResponse)
async def update_my_preferences(
    obj_in: UserPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update current user's preferences"""
    user_id = str(current_user.id)
    # get_or_create garantiza que siempre exista la fila antes de actualizar
    crud_user_preferences.get_or_create(db, user_id)
    preferences = crud_user_preferences.update_by_user(db, user_id, obj_in)
    if not preferences:
        raise HTTPException(status_code=400, detail="Could not update preferences")

    # Invalidar caché para que el próximo GET devuelva datos frescos
    cache.delete(f"config:preferences:user:{current_user.id}")

    return SuccessResponse(
        status="success",
        message="Preferencias actualizadas",
        data=preferences
    )


@config_router.get("/preferences/user/{user_id}")
async def get_user_preferences(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get preferences for a specific user (admin only).

    Antes la dependency era get_current_active_user (cualquier usuario
    autenticado, sin chequeo de rol ni de ownership) pese a que el docstring
    ya decía "admin only" -- un IDOR real: cualquier usuario logueado podía
    leer el theme/idioma/layout de cualquier otro usuario por ID. No es dato
    crítico, pero tampoco era el comportamiento documentado. Se corrigió
    exigiendo ADMIN/SUPER_ADMIN (require_admin) en vez de agregar un chequeo
    de "es su propio user_id" -- no tiene un endpoint /my-preferences
    equivalente con otro proposito de "verse a uno mismo por id", así que el
    caso de uso real es siempre un admin consultando a otro usuario.

    🚀 Optimized with Redis cache (TTL 300s).
    """
    cache_key = f"config:preferences:user:{user_id}"

    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data

    preferences = crud_user_preferences.get_or_create(db, user_id)

    pref_data = {
        "id": preferences.id,
        "user_id": preferences.user_id,
        "theme": preferences.theme,
        "language": preferences.language,
        "font_size": preferences.font_size,
        "date_format": preferences.date_format,
        "time_format": preferences.time_format,
        "currency": preferences.currency,
        "dashboard_layout": preferences.dashboard_layout,
        "email_notifications": preferences.email_notifications,
        "system_notifications": preferences.system_notifications,
        "rows_per_page": preferences.rows_per_page,
        "created_at": preferences.created_at.isoformat() + 'Z' if preferences.created_at else None,
        "updated_at": preferences.updated_at.isoformat() + 'Z' if preferences.updated_at else None,
    }

    cache.set(cache_key, pref_data, ttl=300)
    return pref_data


# ========================================================================
# admin_configuration_router -- prefix /admin/configuration
# Migrado de app/routers/admin_configuration.py, SIN el bloque MODULE_FLAGS
# (extraído a app/shared/feature_flags/ -- ver ese módulo para /modules).
# Prefijo fijado en el propio APIRouter() (antes lo aplicaba el
# include_router(..., prefix="/admin/configuration") del router.py viejo).
# ========================================================================

admin_configuration_router = APIRouter(prefix="/admin/configuration", tags=["admin-configuration"])


@admin_configuration_router.get("/security-policies", response_model=SecurityPoliciesResponse)
async def get_security_policies(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Obtener políticas de seguridad activas"""
    policy = security_policies.get_active(db)

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontraron políticas de seguridad"
        )

    return policy


@admin_configuration_router.post("/security-policies", response_model=SecurityPoliciesResponse, status_code=status.HTTP_201_CREATED)
async def create_security_policies(
    policy_data: SecurityPoliciesCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Crear nuevas políticas de seguridad"""
    policy = security_policies.create(db, **policy_data.model_dump())
    return policy


@admin_configuration_router.put("/security-policies/{policy_id}", response_model=SecurityPoliciesResponse)
async def update_security_policies(
    policy_id: int,
    policy_data: SecurityPoliciesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Actualizar políticas de seguridad"""
    policy = security_policies.update(
        db,
        policy_id,
        **policy_data.model_dump(exclude_unset=True)
    )

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Políticas de seguridad no encontradas"
        )

    return policy


# ========================================================================
# ENDPOINTS - PERMISOS
# ========================================================================

@admin_configuration_router.get("/permissions", response_model=PermissionListResponse)
async def list_permissions(
    skip: int = 0,
    limit: int = 100,
    category: str = Query(None, description="Filtrar por categoría"),
    resource: str = Query(None, description="Filtrar por recurso"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Listar todos los permisos del sistema"""
    if category:
        permissions = access_control_service.get_permissions_by_category(db, category)
    elif resource:
        permissions = access_control_service.get_permissions_by_resource(db, resource)
    else:
        permissions = access_control_service.get_all_permissions(db, skip, limit)

    # Obtener categorías únicas
    categories = list(set(p.permission_category for p in permissions))

    return {
        "total": len(permissions),
        "items": permissions,
        "categories": categories
    }


@admin_configuration_router.get("/permissions/{permission_id}", response_model=PermissionResponse)
async def get_permission(
    permission_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Obtener un permiso por ID"""
    perm = access_control_service.get_permission_by_id(db, permission_id)

    if not perm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permiso no encontrado"
        )

    return perm


@admin_configuration_router.post("/permissions", response_model=PermissionResponse, status_code=status.HTTP_201_CREATED)
async def create_permission(
    permission_data: PermissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Crear nuevo permiso"""
    # Verificar que no exista un permiso con el mismo código
    existing = access_control_service.get_permission_by_code(db, permission_data.permission_code)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ya existe un permiso con el código '{permission_data.permission_code}'"
        )

    perm = access_control_service.create_permission(db, **permission_data.model_dump())
    # El catálogo de permisos cambió — invalidar caché para que el frontend
    # reciba la lista actualizada en la próxima consulta
    invalidate_permissions_cache()
    return perm


@admin_configuration_router.post("/permissions/bulk", response_model=List[PermissionResponse], status_code=status.HTTP_201_CREATED)
async def create_permissions_bulk(
    bulk_data: PermissionBulkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Crear múltiples permisos de una vez"""
    created_permissions = []

    for perm_data in bulk_data.permissions:
        # Verificar que no exista
        existing = access_control_service.get_permission_by_code(db, perm_data.permission_code)
        if not existing:
            perm = access_control_service.create_permission(db, **perm_data.model_dump())
            created_permissions.append(perm)

    # Invalidar una sola vez tras insertar todos los permisos del lote
    if created_permissions:
        invalidate_permissions_cache()

    return created_permissions


@admin_configuration_router.put("/permissions/{permission_id}", response_model=PermissionResponse)
async def update_permission(
    permission_id: uuid.UUID,
    permission_data: PermissionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Actualizar permiso"""
    try:
        perm = access_control_service.update_permission(
            db,
            permission_id,
            **permission_data.model_dump(exclude_unset=True)
        )

        if not perm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Permiso no encontrado"
            )

        # El catálogo cambió — invalidar caché
        invalidate_permissions_cache()
        return perm
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@admin_configuration_router.delete("/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permission(
    permission_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Eliminar permiso"""
    try:
        success = access_control_service.delete_permission(db, permission_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Permiso no encontrado"
            )

        # El catálogo cambió — invalidar caché
        invalidate_permissions_cache()
        return None
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ========================================================================
# ENDPOINTS - CONFIGURACIÓN DE SEGURIDAD (CAPTCHA / TURNSTILE)
# ========================================================================

@admin_configuration_router.get("/turnstile")
async def get_turnstile_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Obtener configuración de Cloudflare Turnstile."""
    enabled = crud_system_configuration.get_by_key(db, "turnstile_enabled")
    site_key = crud_system_configuration.get_by_key(db, "turnstile_site_key")
    # La secret key nunca se devuelve al frontend — solo si está configurada
    secret = crud_system_configuration.get_by_key(db, "turnstile_secret_key")
    return {
        "enabled": bool(enabled.value_boolean) if enabled else False,
        "site_key": site_key.value_string or "" if site_key else "",
        "secret_key_configured": bool(secret and secret.value_string),
    }


@admin_configuration_router.put("/turnstile")
async def update_turnstile_config(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Actualizar configuración de Cloudflare Turnstile."""

    def _upsert(key: str, name: str, dtype: str, encrypted: bool = False, **values):
        cfg = crud_system_configuration.get_by_key(db, key)
        if cfg:
            crud_system_configuration.update(db, key, **values)
        else:
            crud_system_configuration.create(
                db,
                config_key=key,
                config_name=name,
                config_category="security",
                data_type=dtype,
                is_encrypted=encrypted,
                **values,
            )

    if "enabled" in data:
        _upsert("turnstile_enabled", "Turnstile Habilitado", "boolean",
                value_boolean=bool(data["enabled"]))

    if "site_key" in data:
        _upsert("turnstile_site_key", "Turnstile Site Key", "string",
                value_string=str(data["site_key"]))

    if "secret_key" in data and data["secret_key"]:
        _upsert("turnstile_secret_key", "Turnstile Secret Key", "string",
                encrypted=True, value_string=str(data["secret_key"]))

    bump_config_version()
    return {"ok": True}
