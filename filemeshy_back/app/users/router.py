from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func
from uuid import UUID
from app.core.database import get_db
from app.users.schemas import (
    User as UserSchema,
    UserCreate,
    UserUpdate,
    UsersResponse,
    UserRole,
)
from app.shared.schemas.common import SuccessResponse
from app.auth.schemas import SessionsListResponse
from app.users.repository import user as crud_user
from app.users.service import user_service
from app.access_control import service as access_control_service
from app.auth.service import get_current_active_user, invalidate_session_active_cache
from app.access_control.service import has_permission
from app.users.models import User
from app.auth.models import Session as SessionModel
from app.core.security import verify_password, get_password_hash
from app.core.password_validator import password_validator
from app.auth.service import AuditService
from app.audit.service import log_audit
from app.access_control.schemas import (
    UserPermissionOverridesUpdate,
    UserPermissionOverridesResponse,
    PermissionResponse,
)
from app.configuration.schemas import SecurityPoliciesResponse
from app.configuration.service import get_active_security_policies, create_default_security_policies
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
import math

router = APIRouter(prefix="/users", tags=["users"])

# Magic-bytes real (no content-type del header, falsificable), límite de
# tamaño explícito, SVG excluido (puede llevar <script> embebido, stored XSS
# si termina servido desde un bucket público como el avatar).
MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
AVATAR_IMAGE_FORMATS = {"jpeg", "png", "webp", "gif"}


# ===== SCHEMAS PARA CAMBIO DE CONTRASEÑA =====
class ChangePasswordRequest(BaseModel):
    """Schema para solicitud de cambio de contraseña."""
    current_password: str
    new_password: str


@router.get("/stats")
def get_user_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["users.view", "admin.manage"]))
):
    """Obtener estadísticas globales de usuarios (con Redis cache)."""
    from app.core.cache import cache
    from app.core.config import settings
    from sqlalchemy import case
    import logging
    logger = logging.getLogger(__name__)

    # Mismo criterio que list_users: SUPER_ADMIN no debe aparecer ni en los totales
    # ni en el conteo por rol para quien no es SUPER_ADMIN -- cache key propia por
    # nivel para no filtrar el conteo real entre viewers distintos.
    viewer_is_super_admin = bool(current_user.role_obj and current_user.role_obj.name == 'SUPER_ADMIN')
    cache_key = f"users:stats:{'super' if viewer_is_super_admin else 'restricted'}"
    try:
        cached = cache.get(cache_key)
        if cached:
            return cached
    except Exception as e:
        logger.error(f"Cache error (stats): {e}")

    base_query = db.query(User)
    if not viewer_is_super_admin:
        from app.access_control.models import Role
        super_admin_role = db.query(Role.id).filter(Role.name == 'SUPER_ADMIN').first()
        if super_admin_role:
            base_query = base_query.filter(
                (User.role_id != super_admin_role[0]) | (User.role_id.is_(None))
            )

    result = base_query.with_entities(
        func.count(User.id).label("total"),
        func.count(case((User.is_active == True, 1))).label("total_active"),
        func.count(case((User.is_active == False, 1))).label("total_inactive"),
    ).first()

    # Contar por roles
    from app.access_control.models import Role
    role_counts_query = (
        db.query(Role.name, func.count(User.id))
        .outerjoin(User, User.role_id == Role.id)
        .group_by(Role.name)
        .all()
    )
    role_counts = {name: count for name, count in role_counts_query}
    if not viewer_is_super_admin:
        role_counts.pop('SUPER_ADMIN', None)

    stats = {
        "total": result.total or 0,
        "total_active": result.total_active or 0,
        "total_inactive": result.total_inactive or 0,
        "roles": role_counts,
    }

    try:
        ttl = getattr(settings, 'CACHE_TTL_STATS', 60)
        cache.set(cache_key, stats, ttl=ttl)
    except Exception as e:
        logger.error(f"Cache set error (stats): {e}")

    return stats


@router.get("/roles", response_model=List[str])
def get_available_roles(
    current_user: User = Depends(has_permission(["users.create", "users.view", "admin.manage"]))
):
    """Obtener lista de roles disponibles."""
    return [role.value for role in UserRole]


@router.post("/me/change-password", response_model=SuccessResponse)
def change_my_password(
    request: Request,
    password_data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Cambiar contraseña del usuario actual.

    Requiere:
    - Contraseña actual válida
    - Nueva contraseña que cumpla políticas de seguridad
    - Nueva contraseña diferente de las 3 anteriores
    """
    # Verificar contraseña actual
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Contraseña actual incorrecta"
        )

    # Validar nueva contraseña
    is_valid, error_message = password_validator.check_password_reuse(
        new_password=password_data.new_password,
        current_hash=current_user.hashed_password,
        password_history=current_user.password_history or []
    )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message
        )

    # Actualizar contraseña
    # Agregar contraseña actual al historial
    current_user.password_history = password_validator.add_to_history(
        current_hash=current_user.hashed_password,
        password_history=current_user.password_history or []
    )

    # Cambiar a nueva contraseña
    current_user.hashed_password = get_password_hash(password_data.new_password)

    db.commit()

    # Auditoría
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "unknown")

    AuditService.log_password_changed(
        user_id=current_user.id,
        email=current_user.email,
        ip_address=ip_address,
        user_agent=user_agent,
        method="profile"
    )

    return SuccessResponse(
        status=200,
        message="Contraseña actualizada exitosamente"
    )


@router.get("/", response_model=UsersResponse)
@router.get("", response_model=UsersResponse)  # Aceptar ambas formas: /users y /users/
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    include_sessions: bool = Query(False, description="Include active sessions count"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["users.view", "admin.manage"]))
):
    """Lista todos los usuarios con paginación y filtros (optimizado con Redis cache)."""
    from app.core.cache import cache
    import logging
    logger = logging.getLogger(__name__)

    # SUPER_ADMIN es invisible para cualquiera que no sea otro SUPER_ADMIN -- ni en el
    # listado ni en los conteos (decision explicita del usuario, 2026-08-26).
    viewer_is_super_admin = bool(current_user.role_obj and current_user.role_obj.name == 'SUPER_ADMIN')

    # Generate cache key (incluye el nivel del que consulta -- sin esto, la cache de
    # un SUPER_ADMIN se le serviria tal cual a un no-super-admin, o viceversa)
    cache_key = f"users:list:{skip}:{limit}:{search}:{role}:{is_active}:{include_sessions}:{viewer_is_super_admin}"

    # Try cache first
    cached_data = None
    try:
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(f"CACHE HIT for key: {cache_key}")
            return UsersResponse(**cached_data, cached=True)
        else:
            logger.info(f"CACHE MISS for key: {cache_key}")
    except Exception as e:
        logger.error(f"Cache error: {e}")

    # Consulta base
    from sqlalchemy.orm import joinedload
    query = db.query(User).options(joinedload(User.role_obj))

    if not viewer_is_super_admin:
        from app.access_control.models import Role
        super_admin_role = db.query(Role.id).filter(Role.name == 'SUPER_ADMIN').first()
        if super_admin_role:
            query = query.filter(
                (User.role_id != super_admin_role[0]) | (User.role_id.is_(None))
            )

    # Optimize filter order by selectivity (most selective first)
    # 1. is_active filter (high selectivity)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    # 2. Role filter (medium selectivity)
    if role:
        # Buscar el role_id correspondiente al nombre del rol
        role_obj = access_control_service.get_role_by_name(db, role)
        if role_obj:
            query = query.filter(User.role_id == role_obj.id)

    # 3. Search last (lowest selectivity, most expensive)
    if search:
        # Intelligent search: prefix for short queries, full for longer
        if len(search) <= 3:
            search_term = f"{search}%"
        else:
            search_term = f"%{search}%"

        full_name = func.concat(User.first_name, ' ', func.coalesce(User.last_name, ''))
        query = query.filter(
            (User.first_name.ilike(search_term)) |
            (User.last_name.ilike(search_term)) |
            (User.email.ilike(search_term)) |
            (full_name.ilike(search_term))
        )

    # Contar total
    total = query.count()

    # Aplicar paginación y ORDER BY
    users = query.order_by(User.email.asc()).offset(skip).limit(limit).all()

    # Manual serialization (faster than Pydantic)
    user_schemas = []
    for user in users:
        user_data = {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
            "role": user.role_obj.name if user.role_obj else None,
            "role_id": user.role_id,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "sesiones_activas": 0,
        }

        # Include active sessions count only if requested (expensive operation)
        if include_sessions:
            active_sessions_count = db.query(SessionModel).filter(
                SessionModel.user_id == user.id,
                SessionModel.is_active == True,
                SessionModel.expires_at > datetime.utcnow()
            ).count()
            user_data["sesiones_activas"] = active_sessions_count

        user_schemas.append(user_data)

    # Calcular páginas
    page = (skip // limit) + 1 if limit > 0 else 1
    total_pages = math.ceil(total / limit) if limit > 0 else 0

    response_data = {
        "items": user_schemas,
        "total": total,
        "page": page,
        "page_size": limit,
        "total_pages": total_pages,
    }

    # Store in cache with short TTL (60s for security)
    try:
        cache.set(
            cache_key,
            response_data,
            ttl=60  # 1 minute (short for security)
        )
        logger.info(f"CACHE SET for key: {cache_key}")
    except Exception as e:
        logger.error(f"Cache set error: {e}")

    return UsersResponse(**response_data, cached=False)


@router.post("/", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=UserSchema, status_code=status.HTTP_201_CREATED)  # ✅ Aceptar ambas formas
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["users.create", "admin.manage"]))
):
    """Crea un nuevo usuario (requiere permiso users.create o ser superuser)."""
    # Nota: UserCreate no expone `permissions` (solo UserUpdate lo tiene) -- un
    # usuario nuevo siempre recibe los permisos derivados de su role_id
    # (ver users/service.py::UserService.create -> _default_permissions_for_role), nunca una
    # lista a mano vía este endpoint. El hueco equivalente en la actualización
    # de un usuario existente (PUT /users/{id}) sí existía y se corrigió abajo.

    # Verificar si el usuario ya existe
    existing_user = crud_user.get_by_email(db, email=user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El email ya está registrado"
        )

    user = user_service.create(db, obj_in=user_in)
    # Recargar con role_obj para que el schema incluya el campo role
    user = crud_user.get(db, id=user.id) or user

    from app.core.cache import invalidate_users_cache
    invalidate_users_cache()

    log_audit(
        db,
        user_id=str(current_user.id),
        user_email=current_user.email,
        action="CREATE",
        table_name="users",
        record_id=str(user.id),
        new_data={"email": user.email, "first_name": user.first_name, "last_name": user.last_name, "is_active": user.is_active},
    )

    return user


@router.get("/{user_id}", response_model=UserSchema)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtiene un usuario por ID."""
    user = crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    # Un usuario normal solo puede ver su propia información
    # Superusers y usuarios con permisos users.view pueden ver cualquier usuario
    if user.id != current_user.id and not crud_user.is_superuser(current_user):
        user_permissions = current_user.permissions if current_user.permissions else []
        if "users.view" not in user_permissions and "admin.manage" not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para ver este usuario"
            )

    # Agregar conteo de sesiones activas
    active_sessions_count = db.query(SessionModel).filter(
        SessionModel.user_id == user.id,
        SessionModel.is_active == True,
        SessionModel.expires_at > datetime.utcnow()
    ).count()

    user_schema = UserSchema.model_validate(user)
    if user.role_obj:
        user_schema.role = user.role_obj.name
    user_schema.sesiones_activas = active_sessions_count

    return user_schema


@router.put("/{user_id}", response_model=UserSchema)
def update_user(
    user_id: UUID,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Actualiza un usuario."""
    user = crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    user_permissions = current_user.permissions if current_user.permissions else []
    is_superuser = crud_user.is_superuser(current_user)

    # Un usuario normal solo puede actualizar su propia información
    # Superusers y usuarios con permisos users.edit pueden editar cualquier usuario
    if user.id != current_user.id and not is_superuser:
        if "users.edit" not in user_permissions and "admin.manage" not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para actualizar este usuario"
            )

    # CRITICO: cambiar role_id (incluso sobre uno mismo) exige users.manage_roles --
    # antes esto se saltaba por completo en auto-edicion (user.id == current_user.id),
    # permitiendo que cualquier usuario logueado se auto-asignara el rol SUPER_ADMIN
    # vía PUT /users/{su_propio_id}.
    incoming = user_in.model_dump(exclude_unset=True)
    if "role_id" in incoming and not is_superuser:
        if "users.manage_roles" not in user_permissions and "admin.manage" not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para cambiar el rol de este usuario"
            )

    # MAS CRITICO TODAVIA: fijar `permissions` a mano (una lista arbitraria, no
    # derivada de un rol real) exige SUPER_ADMIN -- no alcanza con users.manage_roles
    # ni admin.manage EN LA LISTA. Encontrado en revision adversarial 2026-08-25:
    # con el gate anterior, cualquier ADMIN (que ya trae users.manage_roles de
    # fabrica) podia mandar {"permissions": ["admin.manage"]} y auto-escalarse a
    # privilegios equivalentes a SUPER_ADMIN sin pasar por role_id ni por la tabla
    # role_permissions. Cambiar de ROL sigue permitido con users.manage_roles (eso
    # ya recalcula permissions desde el rol real, ver users/service.py::update); lo que
    # se bloquea es inventar una lista de permisos que no corresponde a ningun rol.
    # OJO: este camino (fijar `permissions` a mano, completo) NO pasa por
    # user_permission_overrides -- si se usa para dar una excepcion individual, se
    # pierde en silencio la proxima vez que cambien los permisos del rol de este
    # usuario (set_permissions_for_role recalcula desde ahi, no desde este payload).
    # Para excepciones que tengan que sobrevivir a eso, usar
    # PUT /users/{id}/permission-overrides (mas abajo), que es lo que usa la UI.
    if "permissions" in incoming and not is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo SUPER_ADMIN puede fijar una lista de permisos manual. Para cambiar el acceso de este usuario, cambiá su rol."
        )

    old_data = {
        "email": user.email, "first_name": user.first_name, "last_name": user.last_name,
        "is_active": user.is_active, "role_id": str(user.role_id) if user.role_id else None,
        "permissions": user.permissions,
    }
    user = user_service.update(db, db_obj=user, obj_in=user_in)
    # Recargar con role_obj para que el schema incluya el campo role
    user = crud_user.get(db, id=user.id) or user

    from app.core.cache import invalidate_users_cache
    invalidate_users_cache()

    log_audit(
        db,
        user_id=str(current_user.id),
        user_email=current_user.email,
        action="UPDATE",
        table_name="users",
        record_id=str(user_id),
        old_data=old_data,
        new_data={
            "email": user.email, "first_name": user.first_name, "last_name": user.last_name,
            "is_active": user.is_active, "role_id": str(user.role_id) if user.role_id else None,
            "permissions": user.permissions,
        },
    )

    return user


# ==================== EXCEPCIONES INDIVIDUALES DE PERMISO ====================
# Capa aditiva sobre role_permissions: un usuario mantiene el rol que tiene, pero
# puede tener permisos agregados/quitados a mano respecto de lo que da ese rol
# (ver access_control/repository.py). Solo SUPER_ADMIN puede tocar esto -- un
# override puede incluir cualquier permiso del catalogo (incluido admin.manage), asi
# que dejarlo en users.manage_roles reabriria la misma superficie de auto-escalacion
# que se cerro en update_user (decision explicita del usuario al retomar este tema).

@router.get("/{user_id}/permission-overrides", response_model=UserPermissionOverridesResponse)
def get_user_permission_overrides(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Excepciones individuales de un usuario + la base de su rol + el catalogo
    completo. Lectura disponible para ADMIN/SUPER_ADMIN (mismo criterio que
    GET /roles/{id}/permissions); solo SUPER_ADMIN puede modificarlas."""
    is_admin_role = current_user.role_obj and current_user.role_obj.name in ['ADMIN', 'SUPER_ADMIN']
    if not is_admin_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver excepciones de permisos"
        )

    user = crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    role_permission_ids = access_control_service.get_permission_ids_for_role(db, user.role_id) if user.role_id else []
    overrides = access_control_service.get_overrides_for_user(db, user_id)
    catalog = access_control_service.get_all_permissions(db, limit=1000, active_only=True)

    return UserPermissionOverridesResponse(
        user_id=user.id,
        role_id=user.role_id,
        role_permission_ids=role_permission_ids,
        grant_ids=[o.permission_id for o in overrides if o.is_granted],
        revoke_ids=[o.permission_id for o in overrides if not o.is_granted],
        catalog=[PermissionResponse.model_validate(p) for p in catalog],
    )


@router.put("/{user_id}/permission-overrides", response_model=UserPermissionOverridesResponse)
def update_user_permission_overrides(
    user_id: UUID,
    payload: UserPermissionOverridesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Reemplaza el set completo de excepciones individuales de un usuario.
    Recalcula User.permissions de inmediato (rol actual +/- las excepciones nuevas)."""
    if not crud_user.is_superuser(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo SUPER_ADMIN puede asignar permisos individuales"
        )

    user = crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    # Dedup (mandar el mismo id 2 veces en la misma lista rompe el UniqueConstraint
    # de user_permission_overrides con un 500 no controlado) preservando el orden.
    grant_ids = list(dict.fromkeys(payload.grant_ids))
    revoke_ids = list(dict.fromkeys(payload.revoke_ids))

    overlap = set(grant_ids) & set(revoke_ids)
    if overlap:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un permiso no puede estar agregado y quitado a la vez"
        )

    requested_ids = set(grant_ids) | set(revoke_ids)
    if requested_ids:
        from app.access_control.models import Permission
        existing_ids = {
            row[0] for row in db.query(Permission.id).filter(Permission.id.in_(requested_ids)).all()
        }
        missing = requested_ids - existing_ids
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"permission_id inexistente en el catálogo: {', '.join(str(m) for m in missing)}"
            )

    before = access_control_service.get_overrides_for_user(db, user_id)
    before_data = {
        "grant_ids": sorted(str(o.permission_id) for o in before if o.is_granted),
        "revoke_ids": sorted(str(o.permission_id) for o in before if not o.is_granted),
    }

    access_control_service.set_overrides_for_user(
        db, user_id, grant_ids, revoke_ids, created_by_id=current_user.id
    )

    from app.core.cache import invalidate_users_cache
    invalidate_users_cache()

    log_audit(
        db,
        user_id=str(current_user.id),
        user_email=current_user.email,
        action="UPDATE",
        table_name="user_permission_overrides",
        record_id=str(user_id),
        old_data=before_data,
        new_data={
            "grant_ids": sorted(str(i) for i in grant_ids),
            "revoke_ids": sorted(str(i) for i in revoke_ids),
        },
    )

    role_permission_ids = access_control_service.get_permission_ids_for_role(db, user.role_id) if user.role_id else []
    overrides = access_control_service.get_overrides_for_user(db, user_id)
    catalog = access_control_service.get_all_permissions(db, limit=1000, active_only=True)

    return UserPermissionOverridesResponse(
        user_id=user.id,
        role_id=user.role_id,
        role_permission_ids=role_permission_ids,
        grant_ids=[o.permission_id for o in overrides if o.is_granted],
        revoke_ids=[o.permission_id for o in overrides if not o.is_granted],
        catalog=[PermissionResponse.model_validate(p) for p in catalog],
    )


@router.delete("/{user_id}", response_model=SuccessResponse)
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["users.delete", "admin.manage"]))
):
    """Elimina un usuario (requiere permiso users.delete o ser superuser)."""
    user_to_delete = crud_user.get(db, id=user_id)
    if not user_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    old_data = {"email": user_to_delete.email, "first_name": user_to_delete.first_name, "last_name": user_to_delete.last_name}
    crud_user.delete(db, id=user_id)

    from app.core.cache import invalidate_users_cache
    invalidate_users_cache()

    log_audit(
        db,
        user_id=str(current_user.id),
        user_email=current_user.email,
        action="DELETE",
        table_name="users",
        record_id=str(user_id),
        old_data=old_data,
    )

    return SuccessResponse(
        status=200,
        message="Usuario eliminado exitosamente"
    )


# ==================== ENDPOINTS DE SESIONES ====================

@router.get("/{user_id}/sessions", response_model=SessionsListResponse)
def get_user_sessions(
    user_id: UUID,
    include_expired: bool = Query(False, description="Incluir sesiones expiradas"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtener las sesiones activas de un usuario."""
    # Verificar que el usuario existe
    user = crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    # Solo el propio usuario, superusers o usuarios con permisos pueden ver las sesiones
    if user.id != current_user.id and not crud_user.is_superuser(current_user):
        user_permissions = current_user.permissions if current_user.permissions else []
        if "users.view" not in user_permissions and "admin.manage" not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para ver las sesiones de este usuario"
            )

    # Construir query
    query = db.query(SessionModel).filter(SessionModel.user_id == user_id)

    if not include_expired:
        query = query.filter(
            SessionModel.is_active == True,
            SessionModel.expires_at > datetime.utcnow()
        )

    sessions = query.order_by(SessionModel.last_activity.desc()).all()

    return SessionsListResponse(
        items=sessions,
        total=len(sessions)
    )


@router.delete("/{user_id}/sessions/{session_id}", response_model=SuccessResponse)
def revoke_user_session(
    user_id: UUID,
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Cerrar/revocar una sesión específica de un usuario."""
    # Verificar que el usuario existe
    user = crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    # Solo el propio usuario, superusers o usuarios con permisos pueden cerrar sesiones
    if user.id != current_user.id and not crud_user.is_superuser(current_user):
        user_permissions = current_user.permissions if current_user.permissions else []
        if "users.edit" not in user_permissions and "admin.manage" not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para cerrar sesiones de este usuario"
            )

    # Buscar la sesión
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id,
        SessionModel.user_id == user_id
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión no encontrada"
        )

    # Marcar como inactiva
    session.is_active = False
    db.commit()

    invalidate_session_active_cache(session.access_token_jti)

    return SuccessResponse(
        status=200,
        message="Sesión cerrada exitosamente"
    )


@router.delete("/{user_id}/sessions", response_model=SuccessResponse)
def revoke_all_user_sessions(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Cerrar/revocar todas las sesiones activas de un usuario."""
    # Verificar que el usuario existe
    user = crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    # Solo el propio usuario, superusers o usuarios con permisos pueden cerrar sesiones
    if user.id != current_user.id and not crud_user.is_superuser(current_user):
        user_permissions = current_user.permissions if current_user.permissions else []
        if "users.edit" not in user_permissions and "admin.manage" not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para cerrar sesiones de este usuario"
            )

    # Buscar todas las sesiones activas
    sessions = db.query(SessionModel).filter(
        SessionModel.user_id == user_id,
        SessionModel.is_active == True
    ).all()

    count = len(sessions)

    # Marcar todas como inactivas
    for session in sessions:
        session.is_active = False

    db.commit()

    for session in sessions:
        invalidate_session_active_cache(session.access_token_jti)

    return SuccessResponse(
        status=200,
        message=f"{count} sesión(es) cerrada(s) exitosamente"
    )


@router.post("/{user_id}/avatar", response_model=UserSchema)
async def upload_user_avatar(
    user_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["users.edit", "admin.manage"]))
):
    """Subir o reemplazar la foto de perfil de un usuario"""
    user = crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo debe ser una imagen")

    from app.files.service import upload_file, delete_file, is_minio_url
    from app.files.service import compress_image
    from app.files.service import validate_image_content

    if user.avatar and is_minio_url(user.avatar):
        try:
            delete_file(user.avatar)
        except Exception:
            pass

    contents = await file.read()
    # Magic-bytes real (content_type del header es falsificable) + límite de
    # tamaño explícito + SVG excluido: un SVG puede llevar <script> embebido
    # -- stored XSS si termina servido desde un bucket público (avatar).
    try:
        fmt = validate_image_content(contents, allowed_formats=AVATAR_IMAGE_FORMATS, max_size=MAX_AVATAR_SIZE_BYTES)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    contents, ext = compress_image(contents, fmt)
    content_type = "image/webp" if ext == ".webp" else (file.content_type or "image/jpeg")
    url = upload_file(
        path=f"avatars/user_{user_id}",
        content=contents,
        extension=ext,
        content_type=content_type,
    )

    updated = user_service.update(db, db_obj=user, obj_in=UserUpdate(avatar=url))

    from app.core.cache import invalidate_users_cache
    invalidate_users_cache()

    return updated


# ========================================================================
# ROUTER - PREFERENCIAS DE USUARIO (antes app/routers/user_preferences.py)
# ========================================================================
# El prefijo /user/preferences se fija acá mismo (antes se aplicaba en el
# include_router del router.py viejo) -- ver Riesgo de RECON_RIESGOS.md
# sección 2 sobre routers con prefijo fijado en dos lugares distintos.

preferences_router = APIRouter(prefix="/user/preferences", tags=["user-preferences"])


@preferences_router.get("/security-policies", response_model=SecurityPoliciesResponse)
async def get_security_policies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Obtener políticas de seguridad activas del sistema

    Disponible para todos los usuarios autenticados
    """
    policy = get_active_security_policies(db)

    # Si no existe ninguna política, crear una con valores por defecto
    if not policy:
        policy = create_default_security_policies(db)

    return policy
