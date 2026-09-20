"""
Modelos del módulo de configuración: SecurityPolicies, SystemConfiguration,
UserPreferences.

SecurityPolicies fue extraída de app/models/permission.py durante la
migración a monolito modular: ese archivo real definía dos clases (Permission
y SecurityPolicies) que se dividen entre dos módulos distintos -- Permission
fue a app/access_control/models.py, SecurityPolicies queda acá porque es
config de seguridad organizacional consumida por configuration/repository.py
y configuration/router.py.

El resto (SystemConfiguration, UserPreferences) viene de
app/models/configuration.py, fusionado acá tal cual.
"""
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, Text, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base
from app.shared.utils.uuid7 import uuid7


class SecurityPolicies(Base):
    """
    Políticas de seguridad organizacionales
    Aplican a todos los usuarios del sistema
    """
    __tablename__ = "security_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    # Políticas de contraseña
    min_password_length = Column(Integer, nullable=False, server_default="8")  # Longitud mínima
    require_uppercase = Column(Boolean, nullable=False, server_default="true")  # Requerir mayúsculas
    require_lowercase = Column(Boolean, nullable=False, server_default="true")  # Requerir minúsculas
    require_numbers = Column(Boolean, nullable=False, server_default="true")  # Requerir números
    require_special_chars = Column(Boolean, nullable=False, server_default="false")  # Requerir caracteres especiales
    password_expiration_days = Column(Integer, nullable=False, server_default="90")  # Días para expirar contraseña
    password_history = Column(Integer, nullable=False, server_default="5")  # No reutilizar últimas N contraseñas

    # Políticas de sesión
    session_timeout_minutes = Column(Integer, nullable=False, server_default="30")  # Tiempo de inactividad
    max_session_duration_hours = Column(Integer, nullable=False, server_default="8")  # Duración máxima de sesión
    allow_concurrent_sessions = Column(Boolean, nullable=False, server_default="false")  # Permitir sesiones simultáneas
    max_concurrent_sessions = Column(Integer, nullable=True)  # Máximo de sesiones simultáneas

    # Políticas de bloqueo de cuenta
    enable_account_lockout = Column(Boolean, nullable=False, server_default="true")  # Bloquear cuenta
    max_login_attempts = Column(Integer, nullable=False, server_default="5")  # Intentos máximos de login
    lockout_duration_minutes = Column(Integer, nullable=False, server_default="15")  # Duración del bloqueo

    # Autenticación de dos factores (2FA)
    enforce_2fa = Column(Boolean, nullable=False, server_default="false")  # Forzar 2FA para todos
    enforce_2fa_for_admins = Column(Boolean, nullable=False, server_default="true")  # Forzar 2FA solo admins

    # Auditoría y logging
    log_login_attempts = Column(Boolean, nullable=False, server_default="true")  # Registrar intentos de login
    log_password_changes = Column(Boolean, nullable=False, server_default="true")  # Registrar cambios de contraseña
    log_permission_changes = Column(Boolean, nullable=False, server_default="true")  # Registrar cambios de permisos

    # IP y acceso
    enable_ip_whitelist = Column(Boolean, nullable=False, server_default="false")  # Lista blanca de IPs
    allowed_ips = Column(JSON, nullable=True)  # ["192.168.1.1", "10.0.0.1"]
    enable_geo_blocking = Column(Boolean, nullable=False, server_default="false")  # Bloqueo geográfico
    allowed_countries = Column(JSON, nullable=True)  # ["DO", "US"]

    # Notificaciones de seguridad
    notify_on_new_login = Column(Boolean, nullable=False, server_default="true")  # Notificar nuevo login
    notify_on_password_change = Column(Boolean, nullable=False, server_default="true")  # Notificar cambio de contraseña
    notify_on_suspicious_activity = Column(Boolean, nullable=False, server_default="true")  # Actividad sospechosa

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    updated_by = Column(String, nullable=True)


class SystemConfiguration(Base):
    """
    Global system configuration settings
    """
    __tablename__ = "system_configuration"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    # Identificación de configuración
    config_key = Column(String, unique=True, nullable=False, index=True)  # Clave única de configuración
    config_name = Column(String, nullable=False)  # Nombre legible
    config_category = Column(String, nullable=False, index=True)  # profile, security, appearance, billing, finance, users, notifications, reports, company

    # Almacenamiento de valores
    value_string = Column(String, nullable=True)  # Para valores string
    value_number = Column(Numeric(12, 2), nullable=True)  # Para valores numéricos
    value_boolean = Column(Boolean, nullable=True)  # Para booleanos
    value_json = Column(JSON, nullable=True)  # Para objetos/arrays complejos

    # Metadatos
    description = Column(Text, nullable=True)  # Descripción de la configuración
    data_type = Column(String, nullable=False)  # string, number, boolean, json, array
    is_encrypted = Column(Boolean, nullable=False, server_default="false")  # Datos sensibles (contraseñas, API keys)
    is_readonly = Column(Boolean, nullable=False, server_default="false")  # Config del sistema no modificables

    # Versionamiento y auditoría
    version = Column(Integer, nullable=False, server_default="1")  # Versión del config
    updated_by = Column(String, nullable=True)  # Usuario que actualizó
    updated_at = Column(DateTime, nullable=False, server_default=func.now())  # Última actualización
    created_at = Column(DateTime, nullable=False, server_default=func.now())  # Fecha creación

    __table_args__ = (
        Index('ix_system_configuration_key', 'config_key', unique=True),
        Index('ix_system_configuration_category', 'config_category'),
    )


class UserPreferences(Base):
    """
    User-specific preferences and settings
    """
    __tablename__ = "user_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    # Referencia del usuario
    user_id = Column(String, nullable=False, index=True)  # ID del usuario

    # Preferencias de apariencia
    theme = Column(String, nullable=False, server_default="auto")  # light, dark, auto
    language = Column(String, nullable=False, server_default="es-DO")  # Idioma (código locale)
    font_size = Column(String, nullable=False, server_default="mediano")  # pequeño, mediano, grande
    date_format = Column(String, nullable=False, server_default="DD/MM/YYYY")  # Formato fecha
    time_format = Column(String, nullable=False, server_default="HH:MM:SS")  # Formato hora
    currency = Column(String, nullable=False, server_default="DOP")  # Moneda (código)

    # Preferencias del dashboard
    dashboard_layout = Column(JSON, nullable=True)  # Configuración de widgets del dashboard
    active_kpis = Column(JSON, nullable=True)  # KPIs a mostrar
    default_dashboard_period = Column(String, nullable=True)  # hoy, semana, mes, trimestre, año
    real_time_updates = Column(Boolean, nullable=False, server_default="true")  # Actualizaciones en tiempo real
    update_interval = Column(Integer, nullable=True)  # Intervalo actualización en segundos

    # Preferencias de notificaciones
    email_notifications = Column(Boolean, nullable=False, server_default="true")  # Notificaciones por email
    system_notifications = Column(Boolean, nullable=False, server_default="true")  # Notificaciones del sistema
    notification_types = Column(JSON, nullable=True)  # {sales: true, purchases: false, ...}
    daily_summary = Column(Boolean, nullable=False, server_default="false")  # Resumen diario
    weekly_summary = Column(Boolean, nullable=False, server_default="false")  # Resumen semanal
    monthly_summary = Column(Boolean, nullable=False, server_default="false")  # Resumen mensual

    # Preferencias de datos
    rows_per_page = Column(Integer, nullable=False, server_default="50")  # Filas por página en tablas
    default_view = Column(String, nullable=True)  # table, grid, kanban, etc.
    auto_refresh = Column(Boolean, nullable=False, server_default="false")  # Auto-actualizar datos
    auto_refresh_interval = Column(Integer, nullable=True)  # Intervalo en segundos

    # Preferencias de exportación
    export_format = Column(String, nullable=True)  # pdf, excel, csv
    include_charts = Column(Boolean, nullable=False, server_default="true")  # Incluir gráficos en exportación
    include_summary = Column(Boolean, nullable=False, server_default="true")  # Incluir resumen

    # Configuración personalizada
    custom_preferences = Column(JSON, nullable=True)  # Preferencias custom adicionales

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.now())  # Fecha creación
    updated_at = Column(DateTime, nullable=False, server_default=func.now())  # Última actualización

    __table_args__ = (
        Index('ix_user_preferences_user_id', 'user_id'),
    )
