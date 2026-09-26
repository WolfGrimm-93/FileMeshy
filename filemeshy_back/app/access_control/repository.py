"""
Acceso a datos de access_control: catálogo de roles (CRUDRole), catálogo de
permisos (CRUDPermission), asignación rol<->permiso (role_permissions) y
excepciones individuales de permiso por usuario (user_permission_overrides).

User.permissions sigue siendo lo que lee has_permission() en cada request (no se
hace join contra role_permissions en runtime, por costo) -- pero se recalcula
automaticamente en 2 momentos:
1. Al cambiar el role_id de un usuario (ver app/users/service.py).
2. Al cambiar el set de permisos de un rol (ver set_permissions_for_role: recalcula
   a TODOS los usuarios de ese rol, en la misma transaccion).
"""
from typing import List, Optional
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.access_control.models import Permission, Role, RolePermission, UserPermissionOverride
from app.access_control.schemas import RoleCreate, RoleUpdate


# ========================================================================
# ROLES
# ========================================================================

class CRUDRole:
    """CRUD operations para Role"""

    def get(self, db: Session, role_id: UUID) -> Optional[Role]:
        """Obtener rol por ID"""
        return db.query(Role).filter(Role.id == role_id).first()

    def get_by_name(self, db: Session, name: str) -> Optional[Role]:
        """Obtener rol por nombre"""
        return db.query(Role).filter(Role.name == name.upper()).first()

    def get_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = False,
        include_system: bool = True
    ) -> List[Role]:
        """
        Listar todos los roles

        Args:
            skip: Registros a saltar
            limit: Límite de registros
            active_only: Solo roles activos
            include_system: Incluir roles del sistema
        """
        query = db.query(Role)

        if active_only:
            query = query.filter(Role.is_active == True)

        if not include_system:
            query = query.filter(Role.is_system == False)

        return query.offset(skip).limit(limit).all()

    def get_system_roles(self, db: Session) -> List[Role]:
        """Obtener solo roles del sistema"""
        return db.query(Role).filter(
            Role.is_system == True,
            Role.is_active == True
        ).all()

    def get_custom_roles(self, db: Session) -> List[Role]:
        """Obtener solo roles personalizados (no del sistema)"""
        return db.query(Role).filter(
            Role.is_system == False
        ).all()

    def create(
        self,
        db: Session,
        obj_in: RoleCreate,
        created_by_id: Optional[int] = None
    ) -> Role:
        """
        Crear nuevo rol

        Args:
            db: Session de base de datos
            obj_in: Datos del rol a crear
            created_by_id: ID del usuario que crea el rol

        Raises:
            HTTPException: Si el nombre ya existe
        """
        # Verificar que el nombre no exista
        existing = self.get_by_name(db, obj_in.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe un rol con el nombre '{obj_in.name}'"
            )

        # Ronda 12: permission_ids (fuente real de permisos, tabla
        # role_permissions). Se validan ANTES de crear nada -- un id
        # inexistente aborta con 422 y no queda ningún rol a medias.
        permission_ids = list(dict.fromkeys(obj_in.permission_ids or []))  # sin duplicados, conserva orden
        if permission_ids:
            active_by_id = {
                row[0]: row[1]
                for row in db.query(Permission.id, Permission.is_active).filter(Permission.id.in_(permission_ids)).all()
            }
            # Inexistentes o inactivos (el catálogo del GET solo muestra activos).
            invalid = [str(pid) for pid in permission_ids if not active_by_id.get(pid)]
            if invalid:
                shown = ", ".join(invalid[:20])
                extra = f" y {len(invalid) - 20} más" if len(invalid) > 20 else ""
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Permisos inexistentes o inactivos en permission_ids: {shown}{extra}"
                )

        # Crear rol
        role = Role(
            name=obj_in.name.upper(),
            display_name=obj_in.display_name,
            description=obj_in.description,
            permissions=obj_in.permissions or {},
            is_active=obj_in.is_active,
            is_system=False,  # Roles creados por usuarios nunca son del sistema
            created_by_id=created_by_id
        )

        # Alta atómica: rol + role_permissions en UNA sola transacción (un único
        # commit al final). Si algo falla, rollback y no queda ni el rol.
        try:
            db.add(role)
            db.flush()
            if permission_ids:
                set_permissions_for_role(db, role.id, permission_ids, commit=False)
            db.commit()
        except IntegrityError:
            db.rollback()
            # Carrera de nombre: otra alta simultánea ganó entre get_by_name y el
            # INSERT (unique de roles.name) -> mismo 409 que el chequeo previo.
            # Consulta directa (no get_by_name) para confirmar que fue eso y no
            # otra violación de integridad.
            if db.query(Role.id).filter(Role.name == obj_in.name.upper()).first() is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Ya existe un rol con el nombre '{obj_in.name}'"
                )
            raise
        except Exception:
            db.rollback()
            raise
        db.refresh(role)

        return role

    def update(
        self,
        db: Session,
        role_id: UUID,
        obj_in: RoleUpdate
    ) -> Role:
        """
        Actualizar rol

        Args:
            db: Session de base de datos
            role_id: ID del rol a actualizar
            obj_in: Datos a actualizar

        Raises:
            HTTPException: Si el rol no existe o es del sistema
        """
        role = self.get(db, role_id)

        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rol no encontrado"
            )

        # Actualizar campos
        update_data = obj_in.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(role, field, value)

        db.commit()
        db.refresh(role)

        return role

    def delete(self, db: Session, role_id: UUID) -> None:
        """
        Eliminar rol

        Args:
            db: Session de base de datos
            role_id: ID del rol a eliminar

        Raises:
            HTTPException: Si el rol no existe, es del sistema, o tiene usuarios asignados
        """
        role = self.get(db, role_id)

        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rol no encontrado"
            )

        # No permitir eliminar roles del sistema
        if role.is_system:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No se pueden eliminar roles del sistema"
            )

        # Verificar que no tenga usuarios asignados -- User es el modelo de
        # otro módulo (users), delegado a access_control.service para no
        # leerlo directo desde acá (ver ADVERSARIAL_1_REPORTE.md Hallazgo 1).
        users_count = self.count_users(db, role_id)

        if users_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se puede eliminar el rol porque tiene {users_count} usuario(s) asignado(s)"
            )

        db.delete(role)
        db.commit()

    def count_users(self, db: Session, role_id: UUID) -> int:
        """Contar usuarios con este rol -- delegado a access_control.service,
        que a su vez llama a users.service (User es el modelo de otro
        módulo, ver ADVERSARIAL_1_REPORTE.md Hallazgo 1)."""
        from app.access_control.service import count_users_with_role
        return count_users_with_role(db, role_id)

    def has_permission(
        self,
        db: Session,
        role_id: UUID,
        resource: str,
        action: str
    ) -> bool:
        """
        Verificar si un rol tiene un permiso específico

        Args:
            role_id: ID del rol
            resource: Recurso (sales, products, etc.)
            action: Acción (create, read, update, delete)
        """
        role = self.get(db, role_id)

        if not role:
            return False

        return role.has_permission(resource, action)


# Instancia global del CRUD
role = CRUDRole()


# ========================================================================
# CATALOGO DE PERMISOS
# ========================================================================

class CRUDPermission:
    """CRUD para el catalogo de permisos."""

    @staticmethod
    def get(db: Session, permission_id: UUID) -> Optional[Permission]:
        """Obtener permiso por ID."""
        return db.query(Permission).filter(Permission.id == permission_id).first()

    @staticmethod
    def get_by_code(db: Session, permission_code: str) -> Optional[Permission]:
        """Obtener permiso por codigo (ej. 'clients.view')."""
        return db.query(Permission).filter(Permission.permission_code == permission_code).first()

    @staticmethod
    def get_by_category(db: Session, permission_category: str) -> List[Permission]:
        """Obtener todos los permisos de una categoria."""
        return db.query(Permission).filter(Permission.permission_category == permission_category).all()

    @staticmethod
    def get_by_resource(db: Session, resource: str) -> List[Permission]:
        """Obtener todos los permisos de un recurso."""
        return db.query(Permission).filter(Permission.resource == resource).all()

    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100, active_only: bool = False) -> List[Permission]:
        """Obtener todos los permisos."""
        query = db.query(Permission)
        if active_only:
            query = query.filter(Permission.is_active == True)
        return query.order_by(Permission.permission_category, Permission.permission_code).offset(skip).limit(limit).all()

    @staticmethod
    def create(
        db: Session,
        permission_code: str,
        permission_name: str,
        permission_category: str,
        permission_type: str,
        resource: str,
        description: Optional[str] = None,
        access_level: str = "basic",
        is_system: bool = False,
    ) -> Permission:
        """Crear nuevo permiso."""
        db_permission = Permission(
            permission_code=permission_code,
            permission_name=permission_name,
            permission_category=permission_category,
            permission_type=permission_type,
            resource=resource,
            description=description,
            access_level=access_level,
            is_system=is_system,
        )
        db.add(db_permission)
        db.commit()
        db.refresh(db_permission)
        return db_permission

    @staticmethod
    def update(db: Session, permission_id: UUID, **kwargs) -> Optional[Permission]:
        """Actualizar permiso."""
        db_permission = db.query(Permission).filter(Permission.id == permission_id).first()

        if not db_permission:
            return None

        # No permitir actualizar permisos del sistema
        if db_permission.is_system and 'is_system' not in kwargs:
            raise ValueError("No se pueden modificar permisos del sistema")

        for key, value in kwargs.items():
            if hasattr(db_permission, key) and value is not None:
                setattr(db_permission, key, value)

        db.commit()
        db.refresh(db_permission)
        return db_permission

    @staticmethod
    def delete(db: Session, permission_id: UUID) -> bool:
        """Eliminar permiso."""
        db_permission = db.query(Permission).filter(Permission.id == permission_id).first()

        if not db_permission:
            return False

        # No permitir eliminar permisos del sistema
        if db_permission.is_system:
            raise ValueError("No se pueden eliminar permisos del sistema")

        db.delete(db_permission)
        db.commit()
        return True


# Instancia global
permission = CRUDPermission()


# ========================================================================
# ASIGNACION ROL <-> PERMISO (tabla role_permissions)
# ========================================================================

def get_permission_codes_for_role(db: Session, role_id: UUID) -> List[str]:
    """Codigos de permiso (ej. 'clients.view') asignados a un rol."""
    rows = (
        db.query(RolePermission)
        .join(RolePermission.permission)
        .filter(RolePermission.role_id == role_id)
        .all()
    )
    return [rp.permission.permission_code for rp in rows]


def get_permission_ids_for_role(db: Session, role_id: UUID) -> List[UUID]:
    rows = db.query(RolePermission.permission_id).filter(RolePermission.role_id == role_id).all()
    return [r[0] for r in rows]


def set_permissions_for_role(
    db: Session, role_id: UUID, permission_ids: List[UUID], commit: bool = True
) -> List[str]:
    """Reemplaza el set completo de permisos de un rol y recalcula User.permissions
    de TODOS los usuarios que tengan ese rol -- sin esto, cambiar los permisos de
    un rol desde la UI no afectaria a nadie que ya estuviera logueado con ese rol
    hasta que se le editara el usuario a mano (mismo bug de fondo que el de
    degradar de rol, pero desde el otro lado).

    El recalculo pasa por `apply_overrides` para cada usuario -- si alguien del rol
    tiene una excepcion individual cargada (user_permission_overrides), esta edicion
    ya no se la borra (antes si lo hacia, sobreescribiendo directo con `normalized`).

    `commit=False` (Ronda 12): no commitea -- lo usa `CRUDRole.create` para que el alta
    del rol y sus permisos vivan en la misma transacción."""
    from app.access_control.service import permission_mapper, recalculate_users_permissions_for_role

    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
    db.flush()

    for pid in permission_ids:
        db.add(RolePermission(role_id=role_id, permission_id=pid))
    db.flush()

    codes = get_permission_codes_for_role(db, role_id)
    normalized = permission_mapper.normalize_permissions(codes, db=db)

    # Recalcular User.permissions de todos los usuarios de este rol -- User es
    # el modelo de otro módulo, delegado a access_control.service (que a su
    # vez llama a users.service), ver ADVERSARIAL_1_REPORTE.md Hallazgo 1.
    recalculate_users_permissions_for_role(db, role_id, normalized)

    if commit:
        db.commit()
    return normalized


# ========================================================================
# EXCEPCIONES INDIVIDUALES DE PERMISO POR USUARIO (user_permission_overrides)
# ========================================================================
# Complementa a role_permissions: un usuario mantiene el rol que tiene (ej. CAJERO) pero
# puede tener permisos agregados o quitados a mano respecto de lo que da ese rol --
# User.permissions (el cache que lee has_permission() en cada request) se recalcula como
# permisos_del_rol UNION agregados MENOS quitados, nunca como un reemplazo directo. Asi
# editar los permisos de un rol (set_permissions_for_role de acá arriba) no
# borra las excepciones de nadie.

def get_overrides_for_user(db: Session, user_id: UUID) -> List[UserPermissionOverride]:
    """Excepciones cargadas para un usuario (agregados y quitados, sin resolver)."""
    return (
        db.query(UserPermissionOverride)
        .filter(UserPermissionOverride.user_id == user_id)
        .all()
    )


def apply_overrides(db: Session, base_permission_codes: List[str], user_id: UUID) -> List[str]:
    """Recalcula el set efectivo de permisos de un usuario: los del rol +/- sus
    excepciones individuales, normalizado contra el catalogo real (`permissions`)."""
    from app.access_control.service import permission_mapper

    overrides = (
        db.query(UserPermissionOverride)
        .join(UserPermissionOverride.permission)
        .filter(UserPermissionOverride.user_id == user_id)
        .all()
    )
    codes = set(base_permission_codes)
    for o in overrides:
        code = o.permission.permission_code
        if o.is_granted:
            codes.add(code)
        else:
            codes.discard(code)
    return permission_mapper.normalize_permissions(sorted(codes), db=db)


def set_overrides_for_user(
    db: Session,
    user_id: UUID,
    grant_ids: List[UUID],
    revoke_ids: List[UUID],
    created_by_id: UUID = None,
) -> List[str]:
    """Reemplaza el set completo de excepciones de un usuario y recalcula su
    User.permissions efectivo (rol actual +/- las excepciones nuevas) en la misma
    transaccion."""
    from app.access_control.service import sync_permissions_for_user

    db.query(UserPermissionOverride).filter(UserPermissionOverride.user_id == user_id).delete()
    db.flush()

    for pid in grant_ids:
        db.add(UserPermissionOverride(user_id=user_id, permission_id=pid, is_granted=True, created_by_id=created_by_id))
    for pid in revoke_ids:
        db.add(UserPermissionOverride(user_id=user_id, permission_id=pid, is_granted=False, created_by_id=created_by_id))
    db.flush()

    # Recalcular y guardar User.permissions -- User es el modelo de otro
    # módulo, delegado a access_control.service (que a su vez llama a
    # users.service), ver ADVERSARIAL_1_REPORTE.md Hallazgo 1.
    effective = sync_permissions_for_user(db, user_id)

    db.commit()
    return effective
