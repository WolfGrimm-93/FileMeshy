"""Schemas del módulo de configuración: SecurityPolicies + SystemConfiguration/
UserPreferences, fusionados desde app/schemas/security_policies.py
y app/schemas/configuration.py durante la migración a monolito modular.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


# ================ SECURITY POLICIES ================
class SecurityPoliciesBase(BaseModel):
    """Base schema para políticas de seguridad"""
    min_password_length: int = Field(8, ge=6, le=32, description="Longitud mínima de contraseña")
    require_uppercase: bool = Field(True, description="Requerir mayúsculas")
    require_lowercase: bool = Field(True, description="Requerir minúsculas")
    require_numbers: bool = Field(True, description="Requerir números")
    require_special_chars: bool = Field(True, description="Requerir caracteres especiales")
    password_expiration_days: int = Field(90, ge=0, description="Días antes de expirar contraseña")
    password_history: int = Field(5, ge=0, description="Número de contraseñas a recordar")
    session_timeout_minutes: int = Field(30, ge=5, description="Timeout de sesión en minutos")
    max_session_duration_hours: int = Field(8, ge=1, description="Duración máxima de sesión en horas")
    allow_concurrent_sessions: bool = Field(False, description="Permitir sesiones simultáneas")
    max_concurrent_sessions: Optional[int] = Field(None, description="Máximo de sesiones simultáneas")
    enable_account_lockout: bool = Field(True, description="Habilitar bloqueo de cuenta")
    max_login_attempts: int = Field(5, ge=1, description="Intentos máximos de login")
    lockout_duration_minutes: int = Field(15, ge=1, description="Duración del bloqueo en minutos")
    enforce_2fa: bool = Field(False, description="Forzar 2FA para todos")
    enforce_2fa_for_admins: bool = Field(True, description="Forzar 2FA solo para admins")
    log_login_attempts: bool = Field(True, description="Registrar intentos de login")
    log_password_changes: bool = Field(True, description="Registrar cambios de contraseña")
    log_permission_changes: bool = Field(True, description="Registrar cambios de permisos")
    enable_ip_whitelist: bool = Field(False, description="Habilitar lista blanca de IPs")
    allowed_ips: Optional[List[str]] = Field(None, description="IPs permitidas")
    enable_geo_blocking: bool = Field(False, description="Habilitar bloqueo geográfico")
    allowed_countries: Optional[List[str]] = Field(None, description="Países permitidos")
    notify_on_new_login: bool = Field(True, description="Notificar nuevo login")
    notify_on_password_change: bool = Field(True, description="Notificar cambio de contraseña")
    notify_on_suspicious_activity: bool = Field(True, description="Notificar actividad sospechosa")


class SecurityPoliciesCreate(SecurityPoliciesBase):
    """Schema para crear políticas de seguridad"""
    pass


class SecurityPoliciesUpdate(BaseModel):
    """Schema para actualizar políticas de seguridad"""
    min_password_length: Optional[int] = Field(None, ge=6, le=32)
    require_uppercase: Optional[bool] = None
    require_lowercase: Optional[bool] = None
    require_numbers: Optional[bool] = None
    require_special_chars: Optional[bool] = None
    password_expiration_days: Optional[int] = Field(None, ge=0)
    password_history: Optional[int] = Field(None, ge=0)
    session_timeout_minutes: Optional[int] = Field(None, ge=5)
    max_session_duration_hours: Optional[int] = Field(None, ge=1)
    allow_concurrent_sessions: Optional[bool] = None
    max_concurrent_sessions: Optional[int] = None
    enable_account_lockout: Optional[bool] = None
    max_login_attempts: Optional[int] = Field(None, ge=1)
    lockout_duration_minutes: Optional[int] = Field(None, ge=1)
    enforce_2fa: Optional[bool] = None
    enforce_2fa_for_admins: Optional[bool] = None
    log_login_attempts: Optional[bool] = None
    log_password_changes: Optional[bool] = None
    log_permission_changes: Optional[bool] = None
    enable_ip_whitelist: Optional[bool] = None
    allowed_ips: Optional[List[str]] = None
    enable_geo_blocking: Optional[bool] = None
    allowed_countries: Optional[List[str]] = None
    notify_on_new_login: Optional[bool] = None
    notify_on_password_change: Optional[bool] = None
    notify_on_suspicious_activity: Optional[bool] = None


class SecurityPoliciesResponse(SecurityPoliciesBase):
    """Schema para respuesta de políticas de seguridad"""
    id: UUID
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ================ ENUMS (SystemConfiguration / UserPreferences) ================
class ConfigCategory(str, Enum):
    PROFILE = "profile"
    SECURITY = "security"
    APPEARANCE = "appearance"
    PRIVACY = "privacy"
    BILLING = "billing"
    FINANCE = "finance"
    USERS = "users"
    NOTIFICATIONS = "notifications"
    REPORTS = "reports"
    COMPANY = "company"


class DataType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    JSON = "json"
    ARRAY = "array"


class Theme(str, Enum):
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class Language(str, Enum):
    ES_DO = "es-DO"
    EN_US = "en-US"
    ES_ES = "es-ES"


# ================ SYSTEM CONFIGURATION ================
class SystemConfigurationBase(BaseModel):
    config_key: str = Field(..., min_length=1, max_length=255)
    config_name: str = Field(..., min_length=1, max_length=255)
    config_category: ConfigCategory
    description: Optional[str] = None
    data_type: DataType
    is_encrypted: bool = False
    is_readonly: bool = False
    value_string: Optional[str] = None
    value_number: Optional[float] = None
    value_boolean: Optional[bool] = None
    value_json: Optional[Dict[str, Any]] = None


class SystemConfigurationCreate(SystemConfigurationBase):
    pass


class SystemConfigurationUpdate(BaseModel):
    config_name: Optional[str] = None
    description: Optional[str] = None
    value_string: Optional[str] = None
    value_number: Optional[float] = None
    value_boolean: Optional[bool] = None
    value_json: Optional[Dict[str, Any]] = None


# ================ USER PREFERENCES ================
class NotificationTypeConfig(BaseModel):
    sales: bool = True
    purchases: bool = True
    inventory: bool = True
    finance: bool = False
    users: bool = False
    reports: bool = False


class UserPreferencesBase(BaseModel):
    theme: Theme = Theme.AUTO
    language: Language = Language.ES_DO
    font_size: str = "mediano"
    date_format: str = "DD/MM/YYYY"
    time_format: str = "HH:MM:SS"
    currency: str = "DOP"
    rows_per_page: int = 50
    email_notifications: bool = True
    system_notifications: bool = True
    real_time_updates: bool = True
    auto_refresh: bool = False


class UserPreferencesCreate(UserPreferencesBase):
    user_id: str
    dashboard_layout: Optional[Dict[str, Any]] = None
    active_kpis: Optional[List[str]] = None
    notification_types: Optional[NotificationTypeConfig] = None
    custom_preferences: Optional[Dict[str, Any]] = None


class UserPreferencesUpdate(BaseModel):
    theme: Optional[Theme] = None
    language: Optional[Language] = None
    font_size: Optional[str] = None
    date_format: Optional[str] = None
    time_format: Optional[str] = None
    currency: Optional[str] = None
    rows_per_page: Optional[int] = None
    email_notifications: Optional[bool] = None
    system_notifications: Optional[bool] = None
    notification_types: Optional[NotificationTypeConfig] = None
    dashboard_layout: Optional[Dict[str, Any]] = None
    active_kpis: Optional[List[str]] = None
    real_time_updates: Optional[bool] = None
    custom_preferences: Optional[Dict[str, Any]] = None


# NOTA (2026-09-12): CompanySettings/PaymentMethodConfig (modelos, schemas,
# CRUD y sus usos en platform/router.py y shared/utils/tenant.py) se borraron
# por completo -- resto de negocio no relacionado confirmado por auditoría de
# arquitectura, sin encaje real en un drive personal.
