"""Capa pública del módulo de configuración.

Wrappers delgados (pass-through, sin lógica nueva) sobre `configuration.repository`,
para que otros módulos dejen de leer `configuration.repository`/`configuration.models`
directo -- violación de la regla de fronteras señalada en la revisión adversarial
(ADVERSARIAL_1_REPORTE.md, Hallazgo 1). Cada función acá es una delegación 1:1 a su
método real en el repository; no se agregó ni se cambió ningún comportamiento.

Cubre los métodos que módulos externos (`auth`, `users`, `platform`, `notifications`,
`shared.feature_flags`, `worker.tasks`) ya llaman hoy sobre
`crud_system_configuration` / `crud_user_preferences` / `security_policies`.
"""
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.configuration.models import SecurityPolicies, SystemConfiguration, UserPreferences
from app.configuration.repository import (
    crud_system_configuration,
    crud_user_preferences,
    security_policies,
)
from app.configuration.schemas import UserPreferencesUpdate


# ================ SYSTEM CONFIGURATION ================

def get_system_config(db: Session, config_key: str) -> Optional[SystemConfiguration]:
    """Obtener una configuración del sistema por su clave."""
    return crud_system_configuration.get_by_key(db, config_key)


def get_system_config_by_category(db: Session, category: str) -> list[SystemConfiguration]:
    """Obtener todas las configuraciones del sistema de una categoría."""
    return crud_system_configuration.get_by_category(db, category)


def get_all_system_config(db: Session) -> list[SystemConfiguration]:
    """Obtener todas las configuraciones del sistema."""
    return crud_system_configuration.get_all(db)


def create_system_config(db: Session, **kwargs: Any) -> SystemConfiguration:
    """Crear una nueva configuración del sistema. Ver `CRUDSystemConfiguration.create`
    para los kwargs aceptados (config_key, config_name, config_category, data_type, ...)."""
    return crud_system_configuration.create(db, **kwargs)


def update_system_config(db: Session, config_key: str, **kwargs: Any) -> Optional[SystemConfiguration]:
    """Actualizar una configuración del sistema por su clave. Ver
    `CRUDSystemConfiguration.update` para los kwargs aceptados."""
    return crud_system_configuration.update(db, config_key, **kwargs)


def delete_system_config(db: Session, config_key: str) -> bool:
    """Eliminar una configuración del sistema por su clave."""
    return crud_system_configuration.delete(db, config_key)


# ================ USER PREFERENCES ================

def get_user_preferences(db: Session, user_id: str) -> Optional[UserPreferences]:
    """Obtener las preferencias de un usuario (None si no existen todavía)."""
    return crud_user_preferences.get_by_user(db, user_id)


def get_or_create_user_preferences(db: Session, user_id: str) -> UserPreferences:
    """Obtener las preferencias de un usuario, creándolas con default si no existen."""
    return crud_user_preferences.get_or_create(db, user_id)


def update_user_preferences(db: Session, user_id: str, obj_in: UserPreferencesUpdate) -> Optional[UserPreferences]:
    """Actualizar las preferencias de un usuario."""
    return crud_user_preferences.update_by_user(db, user_id, obj_in)


# ================ SECURITY POLICIES ================

def get_active_security_policies(db: Session) -> Optional[SecurityPolicies]:
    """Obtener las políticas de seguridad activas (None si no existen todavía)."""
    return security_policies.get_active(db)


def create_default_security_policies(db: Session) -> SecurityPolicies:
    """Crear políticas de seguridad con valores por defecto."""
    return security_policies.create(db)
