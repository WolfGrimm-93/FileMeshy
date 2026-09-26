"""
Router de access_control: gestión de roles, asignación rol<->permiso y
catálogo de permisos.

Fusiona dos routers reales: app/routers/roles.py (montado antes con
prefix="/roles" en el include_router del router.py viejo) y
app/api/v1/endpoints/permissions_catalog.py (que ya traía su propio
APIRouter(prefix="/permissions", tags=["permissions"])). Se exponen ambos
`APIRouter` por separado (roles_router, permissions_router) -- el wiring final
en app/api/v1/router.py decide cómo montarlos, ver Riesgo de RECON_RIESGOS.md
sección 2 sobre routers con prefijo fijado en dos lugares distintos.
"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.service import get_current_active_user
from app.users.models import User
from app.access_control.schemas import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleListResponse,
    RolePermissionCheck,
    RolePermissionCheckResponse,
    RoleSummary,
    RolePermissionsUpdate,
    RolePermissionsResponse,
    PermissionResponse,
)
from app.access_control.repository import role as crud_role, permission as crud_permission
from app.access_control import repository as crud_role_permission
from app.core.cache import invalidate_users_cache, cache
from app.audit.service import log_audit
from app.shared.schemas.common import SuccessResponse


# ========================================================================
# ROUTER - GESTIÓN DE ROLES (antes app/routers/roles.py, prefix="/roles")
# ========================================================================

roles_router = APIRouter()


@roles_router.get("", response_model=RoleListResponse)
async def list_roles(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = Query(False, description="Solo roles activos"),
    include_system: bool = Query(True, description="Incluir roles del sistema"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Listar todos los roles

    Requiere permisos de ADMIN o SUPER_ADMIN
    """
    # Verificar permisos (solo ADMIN y SUPER_ADMIN pueden ver roles)
    if not current_user.role_obj or current_user.role_obj.name not in ['ADMIN', 'SUPER_ADMIN']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver roles"
        )

    roles = crud_role.get_all(
        db,
        skip=skip,
        limit=limit,
        active_only=active_only,
        include_system=include_system
    )

    # Contar usuarios y permisos reales por rol -- `role.permissions` (JSONB) quedó
    # muerto desde que role_permissions es la fuente real (ver access_control/repository.py),
    # así que el conteo tiene que salir de esa tabla, no de `len(role.permissions)`.
    for role in roles:
        role.users_count = crud_role.count_users(db, role.id)
        role.permissions_count = len(crud_role_permission.get_permission_ids_for_role(db, role.id))
        role.can_be_modified = role.can_be_modified()
        role.can_be_deleted = role.can_be_deleted()

    # Estadísticas
    active_count = sum(1 for r in roles if r.is_active)
    system_count = sum(1 for r in roles if r.is_system)

    return {
        "total": len(roles),
        "items": roles,
        "active_count": active_count,
        "system_count": system_count
    }


@roles_router.get("/summary", response_model=List[RoleSummary])
async def list_roles_summary(
    active_only: bool = Query(True, description="Solo roles activos"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Listar roles (resumen para selects/dropdowns)

    Todos los usuarios autenticados pueden ver este listado
    """
    roles = crud_role.get_all(
        db,
        active_only=active_only,
        include_system=True
    )

    return [
        RoleSummary(
            id=role.id,
            name=role.name,
            display_name=role.display_name,
            is_system=role.is_system,
            is_active=role.is_active
        )
        for role in roles
    ]


@roles_router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Obtener rol por ID

    Requiere permisos de ADMIN o SUPER_ADMIN
    """
    # Verificar permisos
    if not current_user.role_obj or current_user.role_obj.name not in ['ADMIN', 'SUPER_ADMIN']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver roles"
        )

    role = crud_role.get(db, role_id)

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rol no encontrado"
        )

    # Agregar información computada
    role.users_count = crud_role.count_users(db, role.id)
    role.permissions_count = len(crud_role_permission.get_permission_ids_for_role(db, role.id))
    role.can_be_modified = role.can_be_modified()
    role.can_be_deleted = role.can_be_deleted()

    return role


@roles_router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    role_in: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Crear nuevo rol

    Solo SUPER_ADMIN puede crear roles.

    `permission_ids` (opcional) asigna permisos reales (tabla role_permissions) en la
    misma transacción del alta; un id inexistente responde 422 y no crea el rol. El
    campo legacy `permissions` (JSONB) no otorga ningún permiso efectivo.
    """
    # Solo SUPER_ADMIN puede crear roles
    if not current_user.role_obj or current_user.role_obj.name != 'SUPER_ADMIN':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo SUPER_ADMIN puede crear roles"
        )

    role = crud_role.create(
        db,
        obj_in=role_in,
        created_by_id=current_user.id
    )

    # Agregar información computada
    role.users_count = 0
    role.permissions_count = len(crud_role_permission.get_permission_ids_for_role(db, role.id))
    role.can_be_modified = True
    role.can_be_deleted = True

    return role


@roles_router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: UUID,
    role_in: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Actualizar rol

    Solo SUPER_ADMIN puede modificar roles.
    No se pueden modificar roles del sistema.
    """
    # Solo SUPER_ADMIN puede modificar roles
    if not current_user.role_obj or current_user.role_obj.name != 'SUPER_ADMIN':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo SUPER_ADMIN puede modificar roles"
        )

    role = crud_role.update(db, role_id, role_in)

    # Agregar información computada
    role.users_count = crud_role.count_users(db, role.id)
    role.permissions_count = len(crud_role_permission.get_permission_ids_for_role(db, role.id))
    role.can_be_modified = role.can_be_modified()
    role.can_be_deleted = role.can_be_deleted()

    return role


@roles_router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Eliminar rol

    Solo SUPER_ADMIN puede eliminar roles.
    No se pueden eliminar roles del sistema ni roles con usuarios asignados.
    """
    # Solo SUPER_ADMIN puede eliminar roles
    if not current_user.role_obj or current_user.role_obj.name != 'SUPER_ADMIN':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo SUPER_ADMIN puede eliminar roles"
        )

    crud_role.delete(db, role_id)

    return None


@roles_router.post("/check-permission", response_model=RolePermissionCheckResponse)
async def check_role_permission(
    check_request: RolePermissionCheck,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Verificar si un rol tiene un permiso específico

    Útil para validaciones en el frontend
    """
    role = crud_role.get(db, check_request.role_id)

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rol no encontrado"
        )

    has_permission = crud_role.has_permission(
        db,
        check_request.role_id,
        check_request.resource,
        check_request.action
    )

    return {
        "has_permission": has_permission,
        "role_name": role.name,
        "resource": check_request.resource,
        "action": check_request.action
    }


# ========================================================================
# ROUTER - ASIGNACIÓN ROL <-> PERMISO (tabla role_permissions)
# ========================================================================

@roles_router.get("/{role_id}/permissions", response_model=RolePermissionsResponse)
async def get_role_permissions(
    role_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Permisos asignados a un rol + catálogo completo, para pintar los
    checkboxes de la pantalla de Gestión de Permisos de una sola consulta.

    Accesible para ADMIN/SUPER_ADMIN (mismo criterio que el resto de /roles) o
    cualquiera con el permiso permissions.manage explícito -- sin el segundo
    camino, un rol nuevo como CONTABLE nunca podría ver esta pantalla aunque se
    le otorgara permissions.manage, porque el chequeo por nombre lo excluía antes
    de llegar a mirar el permiso real (hallazgo de revisión adversarial 2026-08-25).
    """
    user_permissions = current_user.permissions if current_user.permissions else []
    is_admin_role = current_user.role_obj and current_user.role_obj.name in ['ADMIN', 'SUPER_ADMIN']
    has_explicit_permission = "permissions.manage" in user_permissions or "admin.manage" in user_permissions
    if not is_admin_role and not has_explicit_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver permisos de roles"
        )

    role = crud_role.get(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado")

    assigned_ids = crud_role_permission.get_permission_ids_for_role(db, role_id)
    catalog = crud_permission.get_all(db, limit=1000, active_only=True)

    return RolePermissionsResponse(
        role_id=role.id,
        role_name=role.name,
        assigned_permission_ids=assigned_ids,
        catalog=[PermissionResponse.model_validate(p) for p in catalog],
    )


@roles_router.put("/{role_id}/permissions", response_model=RolePermissionsResponse)
async def update_role_permissions(
    role_id: UUID,
    payload: RolePermissionsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Reemplaza el set completo de permisos asignados a un rol.

    Recalcula de inmediato User.permissions de TODOS los usuarios con ese rol
    (ver access_control/repository.py::set_permissions_for_role) -- editar permisos
    acá tiene efecto real e inmediato, a diferencia del viejo Role.permissions
    (JSONB) que no leía nadie.

    Exige SUPER_ADMIN, no alcanza con el permiso `permissions.manage` (hallazgo de
    revisión adversarial): este endpoint puede asignarle CUALQUIER permiso del
    catálogo a un rol, incluido `admin.manage`. Si `permissions.manage` se delegara
    alguna vez a un rol no-super (la propia pantalla de Gestión de Permisos invita a
    hacerlo), cualquier usuario de ese rol podría llamar este endpoint para agregarse
    `admin.manage` a sí mismo -- la misma clase de auto-escalación que se cerró en
    PUT /users/{id}, reabierta por esta ruta paralela. Mismo criterio que
    create_role/update_role/delete_role, ya restringidos a SUPER_ADMIN en este mismo
    archivo.
    """
    if not current_user.role_obj or current_user.role_obj.name != 'SUPER_ADMIN':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo SUPER_ADMIN puede modificar los permisos de un rol"
        )

    role = crud_role.get(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado")

    before_ids = sorted(str(i) for i in crud_role_permission.get_permission_ids_for_role(db, role_id))
    crud_role_permission.set_permissions_for_role(db, role_id, payload.permission_ids)
    invalidate_users_cache()

    after_ids = sorted(str(i) for i in payload.permission_ids)
    log_audit(
        db,
        user_id=str(current_user.id),
        user_email=current_user.email,
        action="UPDATE",
        table_name="role_permissions",
        record_id=str(role_id),
        old_data={"role_name": role.name, "permission_ids": before_ids},
        new_data={"role_name": role.name, "permission_ids": after_ids},
    )

    assigned_ids = crud_role_permission.get_permission_ids_for_role(db, role_id)
    catalog = crud_permission.get_all(db, limit=1000, active_only=True)

    return RolePermissionsResponse(
        role_id=role.id,
        role_name=role.name,
        assigned_permission_ids=assigned_ids,
        catalog=[PermissionResponse.model_validate(p) for p in catalog],
    )


# ========================================================================
# ROUTER - CATÁLOGO DE PERMISOS (antes app/api/v1/endpoints/permissions_catalog.py)
# ========================================================================
# El endpoint lee desde la tabla `permissions` (BD) y cachea el resultado
# en Redis. El caché se invalida automáticamente cada vez que se crea,
# actualiza o elimina un permiso vía /admin/configuration/permissions.

permissions_router = APIRouter(prefix="/permissions", tags=["permissions"])

# Clave Redis para el catálogo de permisos.
# Al cambiar esta constante, cambiar también invalidate_permissions_cache() en core/cache.py.
_CACHE_KEY = "permissions:available"

# TTL largo: los permisos del sistema raramente cambian.
# La invalidación explícita en los endpoints de escritura garantiza consistencia.
_CACHE_TTL = 3600  # 1 hora

# Labels en español — se mantienen aquí porque son UI, no datos de negocio.
# Si se agregan nuevos recursos/acciones al backend, actualizar también estas tablas.
_RESOURCE_LABELS: dict[str, str] = {
    'dashboard':  'Dashboard',
    'files':      'Archivos',
    'folders':    'Carpetas',
    'shares':     'Compartidos',
    'users':      'Usuarios',
    'settings':   'Configuración',
    'workspace':  'Workspace',
    'logs':       'Auditoría',
    'admin':      'Administración',
    'permissions': 'Permisos',
}

_ACTION_LABELS: dict[str, str] = {
    'view':          'Ver',
    'create':        'Crear',
    'edit':          'Editar',
    'delete':        'Eliminar',
    'manage':        'Gestionar (total)',
    'upload':        'Subir',
    'download':      'Descargar',
    'rename':        'Renombrar',
    'move':          'Mover',
    'revoke':        'Revocar',
    'edit_email':    'Configurar email',
    'edit_system':   'Editar sistema',
    'manage_roles':  'Gestionar roles',
}


@permissions_router.get("/available", response_model=SuccessResponse)
def get_available_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Devuelve todos los permisos canónicos activos agrupados por recurso.

    - Lee desde la tabla `permissions` (fuente de verdad en BD).
    - Cachea en Redis (TTL 1 hora) para evitar queries repetidas.
    - El caché se invalida automáticamente al crear/editar/eliminar permisos.
    - Cualquier usuario autenticado puede consultar este endpoint.
    """
    from app.access_control.models import Permission

    # Intentar servir desde caché
    cached = cache.get(_CACHE_KEY)
    if cached is not None:
        return SuccessResponse(
            status="success",
            message="Permisos disponibles obtenidos",
            data=cached,
        )

    # Cache miss — consultar BD
    rows = (
        db.query(Permission)
        .filter(Permission.is_active == True)
        .order_by(Permission.permission_category, Permission.permission_code)
        .all()
    )

    available: dict[str, list[str]] = {}
    for row in rows:
        parts = row.permission_code.split('.', 1)
        if len(parts) != 2:
            continue
        resource, action = parts
        if resource not in available:
            available[resource] = []
        available[resource].append(action)

    payload = {
        "available": available,
        "resource_labels": _RESOURCE_LABELS,
        "action_labels": _ACTION_LABELS,
    }

    # Guardar en caché
    cache.set(_CACHE_KEY, payload, ttl=_CACHE_TTL)

    return SuccessResponse(
        status="success",
        message="Permisos disponibles obtenidos",
        data=payload,
    )
