"""
Sistema de permisos canónico.

Define el formato único y autoritativo de permisos en la aplicación.

Formato: resource.action
Ejemplo: files.view, files.upload, files.delete, folders.create

Esto es la ÚNICA FUENTE DE VERDAD para permisos.
Backend interno puede mapear desde formatos legacy,
pero siempre normaliza a este formato antes de devolver al cliente.

ADVERTENCIA -- agregar un permiso nuevo a este archivo (CANONICAL_PERMISSIONS
y/o ROLE_PERMISSIONS_CANONICAL) NO ALCANZA por sí solo. En runtime,
has_permission() (app/access_control/service.py) NUNCA lee este dict
directo -- lee `User.permissions`, una columna cacheada que se calcula a
partir de las tablas REALES `permissions`/`role_permissions`
(app/access_control/repository.py). Ese cache se recalcula solo cuando cambia
el rol/las excepciones de un usuario puntual -- nunca automáticamente cuando
este archivo cambia. Hace falta correr `scripts/seed_permissions.py` (es
idempotente, seguro de correr las veces que haga falta) para que el permiso
nuevo llegue de verdad a `permissions`/`role_permissions`; hasta entonces,
un ADMIN real recibe 403 aunque el permiso ya esté en este dict y el código
que lo exige ya esté desplegado.

Bug real que motivó esta nota (revisión adversarial, Ronda 7 -- backups,
2026-09-21): se agregó 'backups.view' acá y a ROLE_PERMISSIONS_CANONICAL['ADMIN'],
se desplegó el endpoint que lo exige, y los tests pasaron -- pero nadie corrió
el seed contra la BD real. `SELECT ... FROM permissions WHERE
permission_code='backups.view'` devolvía 0 filas, y un ADMIN real (no
SUPER_ADMIN, que bypasea el chequeo de permisos por completo) recibía 403 en
producción. Los tests no lo agarraron porque usaban `grant_permission()`
(tests/conftest.py) -- bypass directo de la columna JSON, sin pasar por
`role_permissions` -- en vez de `make_real_admin()` (mismo archivo), que sí
ejercita el pipeline completo. Cualquier test que exista específicamente
para confirmar que un permiso nuevo quedó bien conectado de punta a punta
debe usar `make_real_admin()`, no `grant_permission()`.
"""

# ================== PERMISOS CANÓNICOS ==================
# Formato: resource.action
# Cada recurso tiene: view (lectura), create (crear), edit (modificar), delete (eliminar), manage (control total)

CANONICAL_PERMISSIONS = {
    # Dashboard
    'dashboard.view': 'Ver dashboard',

    # Archivos
    'files.view': 'Ver archivos',
    'files.upload': 'Subir archivos',
    'files.download': 'Descargar archivos',
    'files.delete': 'Eliminar archivos',
    'files.rename': 'Renombrar archivos',
    'files.move': 'Mover archivos',

    # Carpetas
    'folders.create': 'Crear carpetas',
    'folders.view': 'Ver carpetas',
    'folders.delete': 'Eliminar carpetas',
    'folders.rename': 'Renombrar carpetas',
    'folders.move': 'Mover carpetas',

    # Compartir (links públicos -- todavía no hay modelo "archivo"/"share" real
    # al que apuntar; PrintShare/PrintToken, que servían de referencia, se
    # borraron por quedar rotos y sin caller tras la poda de negocio)
    'shares.create': 'Crear enlaces para compartir',
    'shares.revoke': 'Revocar enlaces compartidos',
    'shares.manage': 'Gestionar todos los enlaces compartidos',

    # Etiquetas (Ronda 2) -- CRUD de las propias etiquetas (app/tags/router.py).
    # Asignar/quitar etiquetas de un archivo o carpeta puntual NO usa este
    # permiso -- reusa files.view/folders.view, mismo criterio que is_favorite
    # (ver PUT /files/{id}/tags y PUT /folders/{id}/tags en app/files/router.py).
    'tags.manage': 'Gestionar las propias etiquetas',

    # Usuarios
    'users.view': 'Ver usuarios',
    'users.create': 'Crear usuarios',
    'users.edit': 'Editar usuarios',
    'users.delete': 'Eliminar usuarios',
    'users.manage_roles': 'Gestionar roles',

    # Configuración
    'settings.view': 'Ver configuración',
    'settings.edit_email': 'Configurar email',
    'settings.edit_system': 'Editar configuración del sistema',

    # Workspace (config de "empresa" conservada como base de organización)
    'workspace.manage': 'Gestionar configuración del workspace',

    # Logs de auditoría
    'logs.view': 'Ver logs de auditoría',

    # Cuotas de almacenamiento (pantalla admin de límites por usuario)
    'storage_quotas.view': 'Ver cuotas de almacenamiento',
    'storage_quotas.manage': 'Gestionar cuotas de almacenamiento',

    # Backups (Ronda 7) -- pantalla admin de corridas de backup (Postgres/
    # MinIO) + disparo manual (GET/POST /admin/backups, ver
    # app/backups/router.py). Un solo permiso para ambos endpoints -- ver
    # ese router para el porqué (verificar que el mecanismo funciona es
    # parte de "verlo", no una acción de gestión aparte).
    'backups.view': 'Ver y disparar backups del sistema',

    # Permisos especiales
    'admin.manage': 'Acceso administrativo completo',
    'permissions.manage': 'Gestionar catálogo y asignación de permisos',
}


# ================== MAPEOS DESDE FORMATOS LEGACY ==================
# Backend acepta estos formatos internamente pero los mapea al canónico
# Esto permite compatibilidad hacia atrás mientras migramos

# Mapeo desde OAuth scopes (action:resource)
OAUTH_TO_CANONICAL = {
    'read:dashboard': 'dashboard.view',

    'read:files': 'files.view',
    'write:files': 'files.upload',
    'delete:files': 'files.delete',

    'read:folders': 'folders.view',
    'write:folders': 'folders.create',
    'delete:folders': 'folders.delete',

    'read:shares': 'shares.manage',
    'write:shares': 'shares.create',
    'delete:shares': 'shares.revoke',

    'manage:users': 'users.view',
    'create:users': 'users.create',
    'edit:users': 'users.edit',
    'delete:users': 'users.delete',

    'manage:settings': 'settings.view',
    'edit:settings': 'settings.edit_system',

    'manage:roles': 'users.manage_roles',

    'full_access': 'admin.manage',
}

# Mapeo desde formato legacy uppercase
LEGACY_TO_CANONICAL = {
    'view_dashboard': 'dashboard.view',
    'VIEW_DASHBOARD': 'dashboard.view',

    'view_files': 'files.view',
    'VIEW_FILES': 'files.view',
    'upload_files': 'files.upload',
    'UPLOAD_FILES': 'files.upload',
    'download_files': 'files.download',
    'DOWNLOAD_FILES': 'files.download',
    'delete_files': 'files.delete',
    'DELETE_FILES': 'files.delete',
    'rename_files': 'files.rename',
    'RENAME_FILES': 'files.rename',
    'move_files': 'files.move',
    'MOVE_FILES': 'files.move',

    'create_folders': 'folders.create',
    'CREATE_FOLDERS': 'folders.create',
    'view_folders': 'folders.view',
    'VIEW_FOLDERS': 'folders.view',
    'delete_folders': 'folders.delete',
    'DELETE_FOLDERS': 'folders.delete',
    'rename_folders': 'folders.rename',
    'RENAME_FOLDERS': 'folders.rename',
    'move_folders': 'folders.move',
    'MOVE_FOLDERS': 'folders.move',

    'create_shares': 'shares.create',
    'CREATE_SHARES': 'shares.create',
    'revoke_shares': 'shares.revoke',
    'REVOKE_SHARES': 'shares.revoke',
    'manage_shares': 'shares.manage',
    'MANAGE_SHARES': 'shares.manage',

    'view_users': 'users.view',
    'VIEW_USERS': 'users.view',
    'create_users': 'users.create',
    'CREATE_USERS': 'users.create',
    'edit_users': 'users.edit',
    'EDIT_USERS': 'users.edit',
    'delete_users': 'users.delete',
    'DELETE_USERS': 'users.delete',
    'manage_users': 'users.view',
    'MANAGE_USERS': 'users.view',

    'view_settings': 'settings.view',
    'VIEW_SETTINGS': 'settings.view',
    'edit_settings': 'settings.edit_system',
    'EDIT_SETTINGS': 'settings.edit_system',

    'manage_workspace': 'workspace.manage',
    'MANAGE_WORKSPACE': 'workspace.manage',
    'edit_company_settings': 'workspace.manage',

    'manage_roles': 'users.manage_roles',
    'MANAGE_ROLES': 'users.manage_roles',

    'view_logs': 'logs.view',
    'VIEW_LOGS': 'logs.view',

    'manage_permissions': 'permissions.manage',
    'MANAGE_PERMISSIONS': 'permissions.manage',

    'admin': 'admin.manage',
    'ADMIN': 'admin.manage',
    'full_access': 'admin.manage',
    'FULL_ACCESS': 'admin.manage',
}


# ================== PERMISOS POR ROL (FORMATO CANÓNICO) ==================

ROLE_PERMISSIONS_CANONICAL = {
    'SUPER_ADMIN': [
        # Todo
        'admin.manage',
    ],

    'ADMIN': [
        # Dashboard
        'dashboard.view',

        # Archivos
        'files.view',
        'files.upload',
        'files.download',
        'files.delete',
        'files.rename',
        'files.move',

        # Carpetas
        'folders.create',
        'folders.view',
        'folders.delete',
        'folders.rename',
        'folders.move',

        # Compartir
        'shares.create',
        'shares.revoke',
        'shares.manage',

        # Etiquetas
        'tags.manage',

        # Usuarios
        'users.view',
        'users.create',
        'users.edit',
        'users.delete',
        'users.manage_roles',

        # Configuración
        'settings.view',
        'settings.edit_system',
        'workspace.manage',

        # Logs de auditoría
        'logs.view',

        # Cuotas de almacenamiento
        'storage_quotas.view',
        'storage_quotas.manage',

        # Backups (Ronda 7)
        'backups.view',
    ],

    'USER': [
        # Dashboard
        'dashboard.view',

        # Archivos y carpetas (uso básico)
        'files.view',
        'files.upload',
        'files.download',
        'folders.view',

        # Etiquetas -- gestionar las propias es uso básico del Drive, mismo
        # criterio que favoritear (Ronda 1): no debería requerir un rol
        # elevado para que el caso de uso principal de esta ronda sea
        # utilizable por el rol por defecto.
        'tags.manage',
    ],
}


def get_all_canonical_permissions() -> list[str]:
    """Retorna lista de todos los permisos canónicos válidos."""
    return list(CANONICAL_PERMISSIONS.keys())


def is_valid_permission(permission: str) -> bool:
    """Valida si un permiso es válido en formato canónico."""
    return permission in CANONICAL_PERMISSIONS


def get_permissions_for_role(role: str) -> list[str]:
    """Retorna permisos canónicos para un rol."""
    return ROLE_PERMISSIONS_CANONICAL.get(role, [])
