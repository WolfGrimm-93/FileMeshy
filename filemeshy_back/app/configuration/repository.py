"""Repository del módulo de configuración.

Fusiona, durante la migración a monolito modular:
- app/crud/security_policies.py (CRUDSecurityPolicies)
- app/crud/system_configuration.py (CRUDSystemConfiguration)
- app/crud/configuration.py (CRUDUserPreferences)
"""
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.configuration.models import SecurityPolicies, SystemConfiguration, UserPreferences
from app.configuration.schemas import (
    UserPreferencesCreate, UserPreferencesUpdate,
)
from app.shared.repository_base import CRUDBase

# NOTA (2026-09-03): CRUDSystemConfiguration/crud_system_config y
# CRUDPaymentMethodConfig/crud_payment_method se borraron -- solo los
# consumía app/api/v1/endpoints/configuration.py (/config/system-config/* y
# /config/payment-methods/*), borrados por no tener ningún caller real (grep
# exhaustivo, confirmado por revisión adversarial). La configuración de
# sistema real (SMTP, flags, etc) sigue viva vía CRUDSystemConfiguration
# (crud_system_configuration, abajo), una implementación totalmente separada
# que NO se tocó.


class CRUDSecurityPolicies:
    """CRUD para security_policies"""

    @staticmethod
    def get(db: Session, policy_id: int) -> Optional[SecurityPolicies]:
        """Obtener política de seguridad por ID"""
        return db.query(SecurityPolicies).filter(
            SecurityPolicies.id == policy_id
        ).first()

    @staticmethod
    def get_active(db: Session) -> Optional[SecurityPolicies]:
        """Obtener la política de seguridad activa"""
        return db.query(SecurityPolicies).order_by(
            SecurityPolicies.created_at.desc()
        ).first()

    @staticmethod
    def create(db: Session) -> SecurityPolicies:
        """Crear política de seguridad con valores por defecto"""
        db_policy = SecurityPolicies()
        db.add(db_policy)
        db.commit()
        db.refresh(db_policy)
        return db_policy

    @staticmethod
    def update(
        db: Session,
        policy_id: int,
        **kwargs
    ) -> Optional[SecurityPolicies]:
        """Actualizar política de seguridad"""
        db_policy = db.query(SecurityPolicies).filter(
            SecurityPolicies.id == policy_id
        ).first()

        if not db_policy:
            return None

        for key, value in kwargs.items():
            if hasattr(db_policy, key) and value is not None:
                setattr(db_policy, key, value)

        db.commit()
        db.refresh(db_policy)
        return db_policy

    @staticmethod
    def delete(db: Session, policy_id: int) -> bool:
        """Eliminar política de seguridad"""
        db_policy = db.query(SecurityPolicies).filter(
            SecurityPolicies.id == policy_id
        ).first()

        if not db_policy:
            return False

        db.delete(db_policy)
        db.commit()
        return True


# Instancia global
security_policies = CRUDSecurityPolicies()


# Sufijos de config_key que delatan un secreto aunque la fila no tenga
# is_encrypted=True (ver también configuration/router.py::_is_secret_config).
SECRET_KEY_SUFFIXES = ("password", "secret", "secret_key", "api_key", "private_key", "token")

# Subconjunto que además se CIFRA al guardar (sin "token": no hay consumidores
# conocidos de claves *_token que esperen descifrarlas; solo se enmascaran en los GET).
ENCRYPTED_KEY_SUFFIXES = ("password", "secret", "secret_key", "api_key", "private_key")


def is_secret_key(config_key: str) -> bool:
    """Clave cuyo valor debe guardarse cifrado."""
    return (config_key or "").lower().endswith(ENCRYPTED_KEY_SUFFIXES)


class CRUDSystemConfiguration:
    """CRUD para system_configuration"""

    @staticmethod
    def get_by_key(db: Session, config_key: str) -> SystemConfiguration:
        """Obtener configuración por clave"""
        return db.query(SystemConfiguration).filter(
            SystemConfiguration.config_key == config_key
        ).first()

    @staticmethod
    def get_by_category(db: Session, category: str) -> list[SystemConfiguration]:
        """Obtener todas las configuraciones de una categoría"""
        return db.query(SystemConfiguration).filter(
            SystemConfiguration.config_category == category
        ).all()

    @staticmethod
    def get_all(db: Session) -> list[SystemConfiguration]:
        """Obtener todas las configuraciones"""
        return db.query(SystemConfiguration).all()

    @staticmethod
    def create(
        db: Session,
        config_key: str,
        config_name: str,
        config_category: str,
        data_type: str,
        value_string: str = None,
        value_number: float = None,
        value_boolean: bool = None,
        value_json: dict = None,
        description: str = None,
        is_encrypted: bool = False,
        is_readonly: bool = False
    ) -> SystemConfiguration:
        """Crear nueva configuración. Si la fila es secreta (is_encrypted o clave
        tipo password/secret/token) el value_string se CIFRA (Fernet) antes de
        guardarlo -- idempotente si ya venía cifrado."""
        if value_string == "****" and (is_encrypted or (config_key or "").lower().endswith(SECRET_KEY_SUFFIXES)):
            value_string = None  # nunca se guarda la máscara como si fuera el secreto
        if value_string and (is_encrypted or is_secret_key(config_key)):
            from app.core.security import encrypt_secret_if_needed

            value_string = encrypt_secret_if_needed(value_string)
            is_encrypted = True
        db_config = SystemConfiguration(
            config_key=config_key,
            config_name=config_name,
            config_category=config_category,
            data_type=data_type,
            value_string=value_string,
            value_number=value_number,
            value_boolean=value_boolean,
            value_json=value_json,
            description=description,
            is_encrypted=is_encrypted,
            is_readonly=is_readonly
        )
        db.add(db_config)
        db.commit()
        db.refresh(db_config)
        return db_config

    @staticmethod
    def update(
        db: Session,
        config_key: str,
        value_string: str = None,
        value_number: float = None,
        value_boolean: bool = None,
        value_json: dict = None,
        updated_by: str = None
    ) -> SystemConfiguration:
        """Actualizar configuración por clave"""
        db_config = CRUDSystemConfiguration.get_by_key(db, config_key)
        if not db_config:
            return None

        # La máscara reenviada nunca reemplaza un secreto real. Cubre TAMBIÉN las claves que solo
        # se enmascaran (`*_token`, ver SECRET_KEY_SUFFIXES), no solo las que se cifran (Ronda 12d).
        if value_string == "****" and (
            db_config.is_encrypted or (config_key or "").lower().endswith(SECRET_KEY_SUFFIXES)
        ):
            value_string = None
        if value_string is not None:
            if value_string and (db_config.is_encrypted or is_secret_key(config_key)):
                # Secreto: se cifra al guardar (también marca legados en claro como
                # cifrados al re-guardarse; ver docs/operacion.md).
                from app.core.security import encrypt_secret_if_needed

                value_string = encrypt_secret_if_needed(value_string)
                db_config.is_encrypted = True
            db_config.value_string = value_string
        if value_number is not None:
            db_config.value_number = value_number
        if value_boolean is not None:
            db_config.value_boolean = value_boolean
        if value_json is not None:
            db_config.value_json = value_json
        if updated_by:
            db_config.updated_by = updated_by

        db_config.version += 1
        db.commit()
        db.refresh(db_config)
        return db_config

    @staticmethod
    def delete(db: Session, config_key: str) -> bool:
        """Eliminar configuración por clave"""
        db_config = CRUDSystemConfiguration.get_by_key(db, config_key)
        if not db_config:
            return False

        db.delete(db_config)
        db.commit()
        return True


# Instancia global
crud_system_configuration = CRUDSystemConfiguration()


class CRUDUserPreferences(CRUDBase[UserPreferences, UserPreferencesCreate, UserPreferencesUpdate]):
    """CRUD operations for User Preferences"""

    def get_by_user(self, db: Session, user_id: str) -> Optional[UserPreferences]:
        """Get preferences for a specific user"""
        return db.query(UserPreferences).filter(
            UserPreferences.user_id == user_id
        ).first()

    def get_or_create(self, db: Session, user_id: str) -> UserPreferences:
        """Get user preferences or create default if not exists"""
        preferences = self.get_by_user(db, user_id)
        if not preferences:
            obj_in = UserPreferencesCreate(user_id=user_id)
            preferences = self.create(db, obj_in)
        return preferences

    def update_by_user(self, db: Session, user_id: str, obj_in: UserPreferencesUpdate) -> Optional[UserPreferences]:
        """Update preferences for a user"""
        db_obj = self.get_by_user(db, user_id)
        if db_obj:
            update_data = obj_in.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                setattr(db_obj, field, value)
            db_obj.updated_at = datetime.now(timezone.utc)
            db.add(db_obj)
            db.commit()
            db.refresh(db_obj)
        return db_obj


# Instantiate CRUD objects
crud_user_preferences = CRUDUserPreferences(UserPreferences)
