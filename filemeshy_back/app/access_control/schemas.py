"""
Schemas Pydantic del módulo access_control: Role, Permission (catálogo),
RolePermission (asignación rol<->permiso) y excepciones individuales por usuario.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict
from uuid import UUID
from datetime import datetime


# ========================================================================
# ROLES
# ========================================================================

class RoleBase(BaseModel):
    """Schema base para Role"""
    name: str = Field(..., min_length=1, max_length=50, description="Nombre único del rol")
    display_name: str = Field(..., min_length=1, max_length=100, description="Nombre visible")
    description: Optional[str] = Field(None, description="Descripción del rol")
    # JSONB legacy sin lector real (la fuente real de permisos es role_permissions,
    # vía PUT /roles/{id}/permissions) -- se acepta cualquier {recurso: [acciones]}
    # bien tipado sin validar contra un catálogo de acciones acá. Bug real
    # encontrado 2026-08-26: un validador viejo rechazaba con 422 cualquier acción
    # que no fuera 'create/read/update/delete/print/configure/view_logs' -- un
    # vocabulario que no es el real (view/edit/manage/...), así que crear o editar
    # un rol marcando cualquier permiso real desde la UI siempre fallaba.
    permissions: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Permisos granulares por recurso (JSONB legacy, sin efecto real)"
    )
    is_active: bool = Field(True, description="Rol activo")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Valida que el nombre sea uppercase y sin espacios"""
        v = v.strip().upper().replace(' ', '_')
        if not v.replace('_', '').isalnum():
            raise ValueError("El nombre solo puede contener letras, números y guiones bajos")
        return v


class RoleCreate(RoleBase):
    """Schema para crear rol.

    `permission_ids` (Ronda 12) es la forma REAL de asignar permisos al crear:
    se persisten en `role_permissions` dentro de la misma transacción del alta
    (ids inexistentes -> 422 y no se crea el rol). Sin `permission_ids` el rol
    nace con 0 permisos, como antes.

    OJO: el campo heredado `permissions` (JSONB legacy) SIGUE sin efecto real --
    se acepta solo por compatibilidad con clientes viejos; un cliente que envíe
    únicamente `permissions` obtiene un rol con 0 permisos efectivos."""
    permission_ids: Optional[List[UUID]] = Field(
        None,
        max_length=1000,
        description=(
            "IDs de permisos (tabla permissions) a asignar al rol al crearlo, atómicamente. "
            "Máximo 1000; solo permisos existentes y ACTIVOS (422 si no). Nota: PUT "
            "/roles/{id}/permissions no valida activos/existentes de esta forma (comportamiento "
            "previo, sin cambios)."
        ),
    )


class RoleUpdate(BaseModel):
    """Schema para actualizar rol"""
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    permissions: Optional[Dict[str, List[str]]] = None  # JSONB legacy, ver nota en RoleBase
    is_active: Optional[bool] = None


class RoleResponse(RoleBase):
    """Schema de respuesta para Role"""
    id: UUID
    is_system: bool
    created_by_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    # Campos computados
    can_be_modified: bool = Field(
        default=True,
        description="Si el rol puede ser modificado (no es del sistema)"
    )
    can_be_deleted: bool = Field(
        default=True,
        description="Si el rol puede ser eliminado"
    )
    users_count: int = Field(
        default=0,
        description="Cantidad de usuarios con este rol"
    )
    permissions_count: int = Field(
        default=0,
        description="Cantidad de permisos asignados a este rol (tabla role_permissions -- "
        "el campo `permissions` de acá arriba es el JSONB legacy, siempre vacío, no usar para contar)"
    )

    @field_validator('permissions', mode='before')
    @classmethod
    def normalize_legacy_permissions(cls, v):
        """Normaliza datos legados en DB: algunos roles se sembraron con
        permissions=[] en vez de {} (ver scripts/instalacion/cliente_nuevo/01_roles.py,
        ya corregido, y scripts/correcciones/ para los roles ya sembrados). Solo aplica
        en el camino de lectura -- create/update siguen rechazando con 422 vía
        RoleBase.validate_permissions, que no tiene mode='before'."""
        if isinstance(v, list):
            return {}
        return v

    class Config:
        from_attributes = True


class RoleListResponse(BaseModel):
    """Schema para lista de roles"""
    total: int
    items: List[RoleResponse]
    active_count: int = Field(default=0, description="Cantidad de roles activos")
    system_count: int = Field(default=0, description="Cantidad de roles del sistema")


# ========================================================================
# SCHEMAS DE UTILIDAD
# ========================================================================

class RolePermissionCheck(BaseModel):
    """Schema para verificar permisos de un rol"""
    role_id: UUID
    resource: str = Field(..., description="Recurso (sales, products, etc.)")
    action: str = Field(..., description="Acción (create, read, update, delete)")

    @field_validator('action')
    @classmethod
    def validate_action(cls, v: str) -> str:
        valid_actions = ['create', 'read', 'update', 'delete', 'print', 'configure', 'view_logs']
        if v not in valid_actions:
            raise ValueError(f"Acción inválida. Permitidas: {', '.join(valid_actions)}")
        return v


class RolePermissionCheckResponse(BaseModel):
    """Respuesta de verificación de permisos"""
    has_permission: bool
    role_name: str
    resource: str
    action: str


class RoleSummary(BaseModel):
    """Resumen de rol (para selects y dropdowns)"""
    id: UUID
    name: str
    display_name: str
    is_system: bool
    is_active: bool

    class Config:
        from_attributes = True


# ========================================================================
# CATALOGO DE PERMISOS
# ========================================================================
# Los nombres de campo siguen los de app/access_control/models.py::Permission
# (permission_code/permission_name/permission_category/permission_type).

class PermissionBase(BaseModel):
    """Base schema para un permiso del catalogo."""
    permission_code: str = Field(..., min_length=3, max_length=100, description="Codigo unico, formato resource.action (ej. clients.view)")
    permission_name: str = Field(..., min_length=3, max_length=200, description="Nombre legible")
    permission_category: str = Field(..., min_length=1, max_length=50, description="Categoria/recurso (ej. clients, invoices)")
    permission_type: str = Field(..., min_length=1, max_length=20, description="Tipo de accion (read, write, delete, admin)")
    resource: str = Field(..., min_length=1, max_length=100, description="Recurso protegido")
    description: Optional[str] = None
    access_level: str = Field(default="basic", description="basic, advanced, admin")
    is_system: bool = Field(default=False, description="Permiso del sistema (no editable/eliminable)")


class PermissionCreate(PermissionBase):
    """Schema para crear un permiso nuevo en el catalogo -- esto es lo que permite
    que un modulo de negocio nuevo agregue sus permisos sin tocar codigo Python."""
    pass


class PermissionUpdate(BaseModel):
    """Schema para actualizar un permiso existente. permission_code no se puede
    cambiar (rompe cualquier `has_permission([...])` que lo referencie en codigo)."""
    permission_name: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = None
    access_level: Optional[str] = None
    is_active: Optional[bool] = None


class PermissionResponse(PermissionBase):
    """Schema de respuesta para un permiso."""
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PermissionListResponse(BaseModel):
    """Lista de permisos, agrupados por categoria para la UI."""
    total: int
    items: List[PermissionResponse]
    categories: List[str]


class PermissionBulkCreate(BaseModel):
    """Crear varios permisos de una vez (ej. todos los de un modulo nuevo)."""
    permissions: List[PermissionCreate]


# ================ ASIGNACION ROL <-> PERMISO ================
class RolePermissionsUpdate(BaseModel):
    """Reemplaza el set completo de permisos asignados a un rol."""
    permission_ids: List[UUID] = Field(default_factory=list)


class RolePermissionsResponse(BaseModel):
    """Permisos asignados a un rol, mas el catalogo completo agrupado por
    categoria para que el frontend pinte los checkboxes de una sola consulta."""
    role_id: UUID
    role_name: str
    assigned_permission_ids: List[UUID]
    catalog: List[PermissionResponse]


# ================ EXCEPCIONES INDIVIDUALES DE PERMISO POR USUARIO ================
class UserPermissionOverridesUpdate(BaseModel):
    """Reemplaza el set completo de excepciones individuales de un usuario --
    permisos agregados sobre su rol (grant_ids) y permisos quitados de su rol
    (revoke_ids). Un mismo permission_id no puede estar en ambas listas."""
    grant_ids: List[UUID] = Field(default_factory=list)
    revoke_ids: List[UUID] = Field(default_factory=list)


class UserPermissionOverridesResponse(BaseModel):
    """Base del rol + excepciones cargadas + catalogo completo, para que el
    frontend calcule el set efectivo (rol UNION agregados MENOS quitados) sin
    una segunda consulta."""
    user_id: UUID
    role_id: Optional[UUID]
    role_permission_ids: List[UUID]
    grant_ids: List[UUID]
    revoke_ids: List[UUID]
    catalog: List[PermissionResponse]
