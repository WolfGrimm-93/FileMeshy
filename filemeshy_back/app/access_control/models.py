"""Modelos del módulo access_control: Permission, Role, RolePermission y
UserPermissionOverride.

`Permission` fue extraída de app/models/permission.py (que mezclaba Permission
con SecurityPolicies -- ver app/configuration/models.py, donde quedó
SecurityPolicies). Se conserva intacta: role_permission.py y
user_permission_override.py tienen FK dura a Permission.id.
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from app.core.database import Base
from app.shared.utils.uuid7 import uuid7


class Permission(Base):
    """
    Permisos granulares del sistema
    Complementa la tabla de roles con permisos específicos
    """
    __tablename__ = "permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    # Identificación del permiso
    permission_code = Column(String(100), unique=True, nullable=False, index=True)  # users.create, sales.read, etc.
    permission_name = Column(String(200), nullable=False)  # Nombre legible
    permission_category = Column(String(50), nullable=False, index=True)  # users, sales, inventory, etc.

    # Descripción
    description = Column(Text, nullable=True)  # Descripción del permiso

    # Tipo de permiso
    permission_type = Column(String(20), nullable=False)  # create, read, update, delete, execute

    # Recurso afectado
    resource = Column(String(100), nullable=False)  # users, sales, products, etc.

    # Nivel de acceso
    access_level = Column(String(20), nullable=False, server_default="basic")  # basic, advanced, admin

    # Estado
    is_active = Column(Boolean, nullable=False, server_default="true")  # Permiso activo
    is_system = Column(Boolean, nullable=False, server_default="false")  # Permiso del sistema (no editable)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('ix_permissions_code', 'permission_code', unique=True),
        Index('ix_permissions_category', 'permission_category'),
        Index('ix_permissions_resource', 'resource'),
    )


class Role(Base):
    """
    Roles de usuario

    Permite crear roles personalizados con permisos granulares.
    Los roles del sistema (USER, ADMIN, SUPER_ADMIN) están marcados con
    is_system=True y no pueden ser editados/eliminados.
    """

    __tablename__ = "roles"

    # ========================================================================
    # IDENTIFICACIÓN
    # ========================================================================

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="ID del rol"
    )
    name = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Nombre único del rol (ej: CAJERO, SUPERVISOR)"
    )

    display_name = Column(
        String(100),
        nullable=False,
        comment="Nombre visible del rol (ej: Cajero Principal)"
    )

    description = Column(
        Text,
        nullable=True,
        comment="Descripción del rol y sus responsabilidades"
    )

    # ========================================================================
    # PERMISOS
    # ========================================================================

    permissions = Column(
        JSONB,
        nullable=False,
        default={},
        server_default='{}',
        comment="""
        Permisos granulares del rol. Estructura:
        {
            "sales": ["create", "read", "update", "delete"],
            "products": ["read"],
            "customers": ["create", "read", "update"],
            "printers": ["print", "configure"],
            "reports": ["read"],
            "users": ["read"]
        }
        """
    )

    # ========================================================================
    # ESTADO Y PROTECCIÓN
    # ========================================================================

    is_system = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Rol del sistema (no editable/eliminable)"
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Rol activo"
    )

    # ========================================================================
    # AUDITORÍA
    # ========================================================================

    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Usuario que creó el rol"
    )

    # ========================================================================
    # TIMESTAMPS
    # ========================================================================

    created_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
        comment="Fecha de creación"
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=datetime.utcnow,
        nullable=False,
        comment="Última actualización"
    )

    # ========================================================================
    # RELACIONES
    # ========================================================================

    # Usuarios con este rol
    users = relationship("User", back_populates="role_obj", foreign_keys="User.role_id")

    # Usuario que creó el rol
    created_by = relationship("User", foreign_keys=[created_by_id])

    # ========================================================================
    # ÍNDICES
    # ========================================================================

    __table_args__ = (
        Index('idx_roles_name', 'name'),
        Index('idx_roles_is_active', 'is_active'),
        Index('idx_roles_is_system', 'is_system'),
    )

    # ========================================================================
    # MÉTODOS AUXILIARES
    # ========================================================================

    def has_permission(self, resource: str, action: str) -> bool:
        """
        Verifica si el rol tiene un permiso específico

        Args:
            resource: Recurso (ej: 'sales', 'products')
            action: Acción (ej: 'create', 'read', 'update', 'delete')

        Returns:
            bool: True si tiene el permiso
        """
        if not self.permissions:
            return False

        resource_permissions = self.permissions.get(resource, [])
        return action in resource_permissions

    def can_be_modified(self) -> bool:
        """Verifica si el rol puede ser modificado (no es del sistema)"""
        return not self.is_system

    def can_be_deleted(self) -> bool:
        """Verifica si el rol puede ser eliminado"""
        return not self.is_system and len(self.users) == 0

    def __repr__(self):
        system_flag = " [SISTEMA]" if self.is_system else ""
        return f"<Role {self.name}{system_flag}>"


class RolePermission(Base):
    """Un permiso asignado a un rol.

    Reemplaza a Role.permissions (JSONB, quedo sin usar y vacio en los 5 roles del
    sistema) y a ROLE_PERMISSIONS_CANONICAL (dict fijo en app/core/permissions.py) como
    fuente real de que permisos tiene cada rol. Un modulo de negocio nuevo agrega sus
    permisos como filas en `permissions` (via la UI de Gestion de Permisos) y los
    asocia a roles aca, sin tocar codigo Python ni redesplegar.
    """

    __tablename__ = "role_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    role = relationship("Role", foreign_keys=[role_id])
    permission = relationship("Permission", foreign_keys=[permission_id])

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
        Index("ix_role_permissions_role_id", "role_id"),
        Index("ix_role_permissions_permission_id", "permission_id"),
    )


class UserPermissionOverride(Base):
    """Una excepcion (agregado o quitado) de permiso para un usuario puntual.

    Complementa a role_permissions (rol<->permiso): el permiso EFECTIVO de un usuario
    (User.permissions, el cache que lee has_permission() en cada request) se calcula como
    los permisos de su rol actual, mas los agregados (is_granted=True) menos los quitados
    (is_granted=False) declarados aca -- nunca reemplazando el rol.
    """

    __tablename__ = "user_permission_overrides"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)
    is_granted = Column(Boolean, nullable=False)  # True = agregado sobre el rol, False = quitado del rol
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    permission = relationship("Permission", foreign_keys=[permission_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        UniqueConstraint("user_id", "permission_id", name="uq_user_permission_override"),
        Index("ix_user_permission_overrides_user_id", "user_id"),
    )
