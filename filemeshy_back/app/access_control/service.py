"""
Servicio de access_control: mapeo/normalización de permisos (PermissionMapper),
la dependencia has_permission (extraída de app/api/deps.py durante la
migración a monolito modular), y wrappers públicos sobre
access_control.repository (roles, permisos, overrides) para que otros
módulos dejen de importar ese repository directo -- violación de fronteras
señalada en la revisión adversarial (ADVERSARIAL_1_REPORTE.md, Hallazgos 1/2/3).
"""

from typing import Callable, List, Optional, Set
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import (
    CANONICAL_PERMISSIONS,
    OAUTH_TO_CANONICAL,
    LEGACY_TO_CANONICAL,
    ROLE_PERMISSIONS_CANONICAL,
)
from app.users.models import User
from app.access_control.models import Role
from app.access_control.repository import (
    role as _role_repo,
    permission as _permission_repo,
    get_permission_codes_for_role as _get_permission_codes_for_role,
    get_permission_ids_for_role as _get_permission_ids_for_role,
    apply_overrides as _apply_overrides,
    get_overrides_for_user as _get_overrides_for_user,
    set_overrides_for_user as _set_overrides_for_user,
)


# ============================================================
# MAPEO DE PERMISOS
# ============================================================

def _valid_permission_codes(db: Optional[Session]) -> Set[str]:
    """Codigos de permiso validos para normalizar contra.

    Si hay `db`, la fuente real es la tabla `permissions` (asi un permiso nuevo
    agregado al catalogo para un modulo de negocio nuevo se reconoce de
    inmediato, sin tocar codigo). `CANONICAL_PERMISSIONS` (dict fijo) queda como
    fallback solo para el puñado de llamadores sin sesion de DB a mano -- no
    deberia ser el camino real en ningun endpoint.
    """
    if db is None:
        return set(CANONICAL_PERMISSIONS.keys())
    from app.access_control.models import Permission
    rows = db.query(Permission.permission_code).filter(Permission.is_active == True).all()
    return {r[0] for r in rows}


class PermissionMapper:
    """Mapea permisos entre formatos."""

    @staticmethod
    def normalize_permissions(permissions: List[str], db: Optional[Session] = None) -> List[str]:
        """
        Normaliza una lista de permisos (en cualquier formato) al formato canónico.

        Entrada: ['read:customers', 'VIEW_CLIENTS', 'view_dashboard', ...]
        Salida:  ['clients.view', 'dashboard.view', ...]

        ✅ Quita duplicados
        ✅ Valida que sean permisos conocidos -- contra la tabla `permissions`
           real si se pasa `db` (recomendado siempre que haya sesion a mano),
           contra CANONICAL_PERMISSIONS (fijo en codigo) si no.
        ✅ Usa solo formato canónico
        """
        canonical_set: Set[str] = set()
        valid_codes = _valid_permission_codes(db)

        for perm in permissions:
            # Intentar mapear desde OAuth
            if perm in OAUTH_TO_CANONICAL:
                canonical_set.add(OAUTH_TO_CANONICAL[perm])
            # Intentar mapear desde legacy
            elif perm in LEGACY_TO_CANONICAL:
                canonical_set.add(LEGACY_TO_CANONICAL[perm])
            # Si ya es canónico (contra el catalogo real en BD), agregarlo
            elif perm in valid_codes:
                canonical_set.add(perm)
            # Si no es conocido, ignorarlo (logging en producción)
            else:
                # En desarrollo, podríamos log: f"Permiso desconocido: {perm}"
                pass

        return sorted(list(canonical_set))

    @staticmethod
    def get_canonical_permissions_for_role(role: str) -> List[str]:
        """
        Retorna los permisos canónicos para un rol.

        Entrada: 'USER'
        Salida: ['dashboard.view', 'files.view', 'files.upload', ...]
        """
        perms = ROLE_PERMISSIONS_CANONICAL.get(role, [])
        # Validar que todos sean canónicos (seguridad)
        return [p for p in perms if p in CANONICAL_PERMISSIONS]

    @staticmethod
    def validate_permission(permission: str) -> bool:
        """
        Valida si un permiso es válido en formato canónico.

        ✅ validate_permission('clients.view')   → True
        ❌ validate_permission('VIEW_CLIENTS')   → False (debe estar normalizado)
        ❌ validate_permission('invalid')        → False
        """
        return permission in CANONICAL_PERMISSIONS

    @staticmethod
    def validate_all_permissions(permissions: List[str]) -> bool:
        """
        Valida que todos los permisos sean canónicos válidos.

        ✅ validate_all_permissions(['clients.view', 'products.create'])   → True
        ❌ validate_all_permissions(['clients.view', 'INVALID'])           → False
        """
        return all(p in CANONICAL_PERMISSIONS for p in permissions)

    @staticmethod
    def has_permission(user_permissions: List[str], required_permission: str) -> bool:
        """
        Verifica si el usuario tiene un permiso específico.

        user_permissions debe estar normalizado al formato canónico.
        """
        return required_permission in user_permissions


# Instancia global
permission_mapper = PermissionMapper()


# ============================================================
# WRAPPERS PÚBLICOS SOBRE access_control.repository
# ============================================================
# Wrappers delgados (pass-through, sin lógica nueva) para que otros módulos
# (auth, users, configuration, platform) dejen de leer access_control.repository
# directo -- ver ADVERSARIAL_1_REPORTE.md Hallazgos 1, 2 y 3.

def get_permission_codes_for_role(db: Session, role_id: UUID) -> List[str]:
    """Códigos de permiso (ej. 'clients.view') asignados a un rol."""
    return _get_permission_codes_for_role(db, role_id)


def get_permission_ids_for_role(db: Session, role_id: UUID) -> List[UUID]:
    """IDs de permiso asignados a un rol."""
    return _get_permission_ids_for_role(db, role_id)


def apply_overrides(db: Session, base_permission_codes: List[str], user_id: UUID) -> List[str]:
    """Recalcula el set efectivo de permisos de un usuario: los de su rol
    +/- sus excepciones individuales (user_permission_overrides)."""
    return _apply_overrides(db, base_permission_codes, user_id)


def get_overrides_for_user(db: Session, user_id: UUID):
    """Excepciones individuales cargadas para un usuario (agregados y
    quitados, sin resolver)."""
    return _get_overrides_for_user(db, user_id)


def set_overrides_for_user(
    db: Session,
    user_id: UUID,
    grant_ids: List[UUID],
    revoke_ids: List[UUID],
    created_by_id: UUID = None,
) -> List[str]:
    """Reemplaza el set completo de excepciones individuales de un usuario y
    recalcula su User.permissions efectivo."""
    return _set_overrides_for_user(db, user_id, grant_ids, revoke_ids, created_by_id=created_by_id)


def get_all_permissions(db: Session, skip: int = 0, limit: int = 100, active_only: bool = False):
    """Catálogo de permisos (paginado)."""
    return _permission_repo.get_all(db, skip=skip, limit=limit, active_only=active_only)


def get_permissions_by_category(db: Session, category: str):
    """Catálogo de permisos filtrado por categoría."""
    return _permission_repo.get_by_category(db, category)


def get_permissions_by_resource(db: Session, resource: str):
    """Catálogo de permisos filtrado por recurso."""
    return _permission_repo.get_by_resource(db, resource)


def get_permission_by_id(db: Session, permission_id):
    """Permiso del catálogo por ID, o None si no existe."""
    return _permission_repo.get(db, permission_id)


def get_permission_by_code(db: Session, permission_code: str):
    """Permiso del catálogo por código, o None si no existe."""
    return _permission_repo.get_by_code(db, permission_code)


def create_permission(db: Session, **fields):
    """Crea un permiso nuevo en el catálogo."""
    return _permission_repo.create(db, **fields)


def update_permission(db: Session, permission_id, **fields):
    """Actualiza un permiso del catálogo, o None si no existe."""
    return _permission_repo.update(db, permission_id, **fields)


def delete_permission(db: Session, permission_id) -> bool:
    """Elimina un permiso del catálogo."""
    return _permission_repo.delete(db, permission_id)


def get_role_by_id(db: Session, role_id: Optional[UUID]) -> Optional[Role]:
    """Rol por ID, o None si `role_id` es falsy o no existe."""
    if not role_id:
        return None
    return _role_repo.get(db, role_id)


def get_role_by_name(db: Session, name: str) -> Optional[Role]:
    """Rol por nombre (case-insensitive, normalizado a mayúsculas)."""
    return _role_repo.get_by_name(db, name)


def get_default_role(db: Session) -> Optional[Role]:
    """Rol por defecto ('USER') para un usuario nuevo sin role_id explícito."""
    return _role_repo.get_by_name(db, "USER")


def count_users_with_role(db: Session, role_id: UUID) -> int:
    """Cuenta usuarios con un rol dado. Delegado a users.service -- User es
    el modelo de otro módulo (import diferido: users.service ya importa este
    módulo a nivel de módulo, un import a nivel de módulo en sentido inverso
    acá crearía un ciclo real, mismo patrón que has_permission() más abajo)."""
    from app.users.service import user_service
    return user_service.count_users_by_role(db, role_id)


def recalculate_users_permissions_for_role(db: Session, role_id: UUID, normalized_codes: List[str]) -> None:
    """Recalcula User.permissions de todos los usuarios de un rol, tras un
    cambio en el set de permisos del rol. Delegado a users.service -- mismo
    motivo de import diferido que count_users_with_role."""
    from app.users.service import user_service
    user_service.recalculate_permissions_for_users_with_role(db, role_id, normalized_codes)


def sync_permissions_for_user(db: Session, user_id: UUID) -> List[str]:
    """Recalcula y guarda User.permissions de un usuario puntual (rol actual
    +/- sus excepciones individuales), tras un cambio en sus excepciones.
    Delegado a users.service -- mismo motivo de import diferido que
    count_users_with_role."""
    from app.users.service import user_service
    return user_service.recalculate_permissions_for_user(db, user_id)


# ============================================================
# DEPENDENCIA has_permission (extraída de app/api/deps.py)
# ============================================================

def has_permission(required_permissions: List[str]) -> Callable:
    """
    Crea una dependencia que verifica si el usuario tiene alguno de los permisos requeridos.
    SUPER_ADMIN tiene acceso a todo (verificado por role_obj.name, no por campo legacy is_superuser).

    Import diferido de auth.service.get_current_active_user -- auth/service.py
    importa permission_mapper (de este módulo) a nivel de módulo, así que un
    import a nivel de módulo en sentido inverso acá crearía un ciclo real. Al
    resolverlo dentro de has_permission() (que se llama al definir cada
    endpoint, no al importar este módulo), ambos módulos ya están completamente
    inicializados para cuando se necesita la referencia real.
    """
    from app.auth.service import get_current_active_user

    async def permission_checker(
        current_user: User = Depends(get_current_active_user)
    ) -> User:
        # SUPER_ADMIN tiene acceso a todo
        if current_user.role_obj and current_user.role_obj.name == 'SUPER_ADMIN':
            return current_user

        # Verificar si el usuario tiene alguno de los permisos requeridos
        user_permissions = current_user.permissions if current_user.permissions else []

        for required_perm in required_permissions:
            if required_perm in user_permissions:
                return current_user

        # Si no tiene ningún permiso requerido, denegar acceso
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos suficientes"
        )

    return permission_checker


