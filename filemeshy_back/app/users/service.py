"""
Servicio de usuarios: orquesta la creación/actualización de usuarios cuando
la lógica cruza a access_control (normalización de permisos al crear, y
recalculo de permisos al cambiar de rol), y expone wrappers públicos sobre
users.repository para que otros módulos (auth) dejen de importarlo directo --
violación de fronteras señalada en la revisión adversarial
(ADVERSARIAL_1_REPORTE.md, Hallazgo 1).

Extraído durante la migración a monolito modular -- antes esta lógica vivía
directo en app/crud/user.py (Riesgo #1 de RECON_RIESGOS.md: "hoy no existe
service.py explícito, la lógica está toda en el CRUD"). app/users/repository.py
se mantiene como acceso a datos puro, sin depender de access_control.service;
este archivo es el único de `users` que llama a access_control.
"""
from typing import Any, Dict, Union
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.users.repository import user as crud_user
from app.users.models import User
from app.users.schemas import UserCreate, UserUpdate
from app.core.security import get_password_hash
from app.access_control.service import (
    permission_mapper,
    get_permission_codes_for_role,
    apply_overrides,
    get_role_by_id,
    get_default_role,
)


class UserService:
    """Orquesta alta/edición de usuarios con normalización de permisos."""

    @staticmethod
    def _default_permissions_for_role(db: Session, role_id) -> list:
        """Retorna los permisos asignados al rol (tabla role_permissions) si no se
        proporcionan explícitamente. Antes leía ROLE_PERMISSIONS_CANONICAL (dict fijo
        en código) -- ahora la fuente real es la asignación rol<->permiso en BD,
        editable desde la pantalla de Gestión de Permisos sin tocar código."""
        if not role_id:
            return []
        role = get_role_by_id(db, role_id)
        if not role:
            return []
        return get_permission_codes_for_role(db, role_id)

    @staticmethod
    def create(db: Session, obj_in: UserCreate) -> User:
        """Crea un nuevo usuario con contraseña hasheada."""
        raw_perms = obj_in.permissions if hasattr(obj_in, 'permissions') and obj_in.permissions else []
        role_id = obj_in.role_id
        if not role_id:
            default_role = get_default_role(db)
            role_id = default_role.id if default_role else None
        # Si no se pasan permisos explícitos, usar los del rol asignado
        if not raw_perms and role_id:
            raw_perms = UserService._default_permissions_for_role(db, role_id)

        return crud_user.insert(
            db,
            email=obj_in.email,
            hashed_password=get_password_hash(obj_in.password),
            first_name=obj_in.first_name,
            last_name=obj_in.last_name,
            phone=obj_in.phone if hasattr(obj_in, 'phone') else None,
            role_id=role_id,
            is_active=obj_in.is_active if hasattr(obj_in, 'is_active') else True,
            permissions=permission_mapper.normalize_permissions(raw_perms, db=db),
        )

    @staticmethod
    def update(
        db: Session,
        db_obj: User,
        obj_in: Union[UserUpdate, Dict[str, Any]]
    ) -> User:
        """Actualiza un usuario, hasheando la contraseña si se proporciona."""
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)

        # Si se está actualizando la contraseña, hashearla
        if "password" in update_data and update_data["password"]:
            hashed_password = get_password_hash(update_data["password"])
            del update_data["password"]
            update_data["hashed_password"] = hashed_password

        # Normalizar permisos si se están actualizando
        if "permissions" in update_data and update_data["permissions"] is not None:
            update_data["permissions"] = permission_mapper.normalize_permissions(update_data["permissions"], db=db)
        elif "role_id" in update_data and update_data["role_id"] != db_obj.role_id:
            # El rol cambio pero no vinieron permisos explicitos en el payload --
            # recalcular desde el rol nuevo. Sin esto, degradar a alguien de ADMIN a
            # CAJERO le dejaba los permisos viejos de ADMIN intactos (bug real
            # encontrado en auditoria 2026-08-25): la UI mostraba el rol nuevo pero
            # has_permission() seguia autorizando contra el permissions viejo.
            # Pasa por apply_overrides para no perder las excepciones individuales
            # que ya tuviera este usuario (user_permission_overrides) al recalcular.
            base_perms = UserService._default_permissions_for_role(db, update_data["role_id"])
            update_data["permissions"] = apply_overrides(db, base_perms, db_obj.id)

        return crud_user.apply_fields(db, db_obj, update_data)

    # ============================================================
    # WRAPPERS PÚBLICOS SOBRE users.repository
    # ============================================================
    # Wrappers delgados (pass-through) para que otros módulos (auth) dejen de
    # importar users.repository directo -- ver ADVERSARIAL_1_REPORTE.md
    # Hallazgo 1.

    @staticmethod
    def get(db: Session, user_id) -> "User | None":
        """Usuario por ID (con role_obj cargado)."""
        return crud_user.get(db, id=user_id)

    @staticmethod
    def get_by_email(db: Session, email: str) -> "User | None":
        """Usuario por email (con role_obj cargado)."""
        return crud_user.get_by_email(db, email=email)

    @staticmethod
    def authenticate(db: Session, email: str, password: str) -> "User | None":
        """Autentica un usuario con email y contraseña (tiempo constante)."""
        return crud_user.authenticate(db, email=email, password=password)

    @staticmethod
    def is_active(user: User) -> bool:
        """Verifica si un usuario está activo."""
        return crud_user.is_active(user)

    @staticmethod
    def is_superuser(user: User) -> bool:
        """Verifica si un usuario tiene el rol SUPER_ADMIN."""
        return crud_user.is_superuser(user)

    # ============================================================
    # WRAPPERS LLAMADOS DESDE access_control.service
    # ============================================================
    # User es el modelo de este módulo -- access_control.service delega acá
    # en vez de leer/mutar la tabla `users` directo (ver
    # ADVERSARIAL_1_REPORTE.md Hallazgo 1, imports de app.users.models desde
    # access_control/repository.py).

    @staticmethod
    def count_users_by_role(db: Session, role_id) -> int:
        """Cuenta usuarios con un rol dado."""
        return db.query(func.count(User.id)).filter(User.role_id == role_id).scalar() or 0

    @staticmethod
    def recalculate_permissions_for_users_with_role(db: Session, role_id, normalized_codes: list) -> None:
        """Recalcula (sin commitear -- el caller es dueño de la transacción)
        el campo `permissions` de cada usuario de un rol dado, tras un cambio
        en el set de permisos de ese rol."""
        affected_users = db.query(User).filter(User.role_id == role_id).all()
        for u in affected_users:
            u.permissions = apply_overrides(db, normalized_codes, u.id)

    @staticmethod
    def recalculate_permissions_for_user(db: Session, user_id) -> list:
        """Recalcula y guarda (sin commitear) el campo `permissions` de un
        usuario puntual (rol actual +/- sus excepciones individuales), tras
        un cambio en sus excepciones (user_permission_overrides)."""
        user = crud_user.get(db, id=user_id)
        role_codes = get_permission_codes_for_role(db, user.role_id) if user and user.role_id else []
        effective = apply_overrides(db, role_codes, user_id)
        if user:
            user.permissions = effective
        return effective


# Instancia global
user_service = UserService()
