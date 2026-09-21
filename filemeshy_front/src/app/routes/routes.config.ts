/**
 * Sistema de Permisos y Rutas (Formato Canónico)
 * 
 * ✅ Backend envía permisos ya normalizados
 * ✅ Frontend solo consulta (resource.action)
 * ✅ SIN mapeos, SIN inferencias
 */

// ==================== PERMISOS ====================
// Formato canónico: resource.action (ej: files.view, files.upload)
//
// ⚠️ ESTE OBJETO DEBE MANTENERSE SINCRONIZADO CON:
//   - Backend: filemeshy_back/app/core/permissions.py → CANONICAL_PERMISSIONS
//   - BD:      tabla `permissions` (poblada por migración 0027)
//   - Validador: shared/utils/permissions-mapper.ts → VALID_PERMISSIONS
//
// Es correcto que esté hardcodeado aquí: TypeScript necesita tipos estáticos
// en tiempo de compilación para proteger rutas y condicionar UI.
// Al agregar un permiso nuevo al backend, agregar la entrada correspondiente aquí.

export const Permission = {
  // Dashboard
  VIEW_DASHBOARD: 'dashboard.view',

  // Archivos
  VIEW_FILES: 'files.view',
  UPLOAD_FILES: 'files.upload',
  DOWNLOAD_FILES: 'files.download',
  DELETE_FILES: 'files.delete',
  RENAME_FILES: 'files.rename',
  MOVE_FILES: 'files.move',

  // Carpetas
  CREATE_FOLDERS: 'folders.create',
  VIEW_FOLDERS: 'folders.view',
  DELETE_FOLDERS: 'folders.delete',
  RENAME_FOLDERS: 'folders.rename',
  MOVE_FOLDERS: 'folders.move',

  // Compartir
  CREATE_SHARES: 'shares.create',
  REVOKE_SHARES: 'shares.revoke',
  MANAGE_SHARES: 'shares.manage',

  // Usuarios
  VIEW_USERS: 'users.view',
  CREATE_USERS: 'users.create',
  EDIT_USERS: 'users.edit',
  DELETE_USERS: 'users.delete',
  MANAGE_ROLES: 'users.manage_roles',

  // Configuración
  VIEW_SETTINGS: 'settings.view',
  EDIT_EMAIL_SETTINGS: 'settings.edit_email',
  MANAGE_SYSTEM_SETTINGS: 'settings.edit_system',

  // Workspace (config de "empresa" conservada como base de organización)
  MANAGE_WORKSPACE: 'workspace.manage',

  VIEW_LOGS: 'logs.view',

  // Super Admin
  FULL_ACCESS: 'admin.manage',

  // Permisos (catálogo + asignación rol<->permiso)
  MANAGE_PERMISSIONS: 'permissions.manage',

  // Cuotas de almacenamiento por usuario
  VIEW_STORAGE_QUOTAS: 'storage_quotas.view',
  MANAGE_STORAGE_QUOTAS: 'storage_quotas.manage',

  // Backups (Postgres + MinIO) -- backups.view es el único permiso del
  // backend, cubre tanto ver el historial como disparar un backup manual.
  VIEW_BACKUPS: 'backups.view',
} as const

export type PermissionType = (typeof Permission)[keyof typeof Permission]

// ==================== ROLES ====================

/**
 * Roles del sistema con permisos asociados.
 * Ahora el backend envía permisos normalizados,
 * así que estos pueden ser de referencia nada más.
 */
// Nota: los nombres de rol siguen los roles reales del backend (ver
// app/core/permissions.py::ROLE_PERMISSIONS_CANONICAL, fuente de verdad).
export const ROLES = {
  SUPER_ADMIN: {
    name: 'Super Administrador',
    permissions: [Permission.FULL_ACCESS],
  },
  ADMIN: {
    name: 'Administrador',
    permissions: [
      Permission.VIEW_DASHBOARD,
      Permission.VIEW_FILES,
      Permission.UPLOAD_FILES,
      Permission.DOWNLOAD_FILES,
      Permission.DELETE_FILES,
      Permission.RENAME_FILES,
      Permission.MOVE_FILES,
      Permission.CREATE_FOLDERS,
      Permission.VIEW_FOLDERS,
      Permission.DELETE_FOLDERS,
      Permission.RENAME_FOLDERS,
      Permission.MOVE_FOLDERS,
      Permission.CREATE_SHARES,
      Permission.REVOKE_SHARES,
      Permission.MANAGE_SHARES,
      Permission.VIEW_USERS,
      Permission.CREATE_USERS,
      Permission.EDIT_USERS,
      Permission.VIEW_SETTINGS,
      Permission.MANAGE_WORKSPACE,
    ],
  },
  USER: {
    name: 'Usuario',
    permissions: [
      Permission.VIEW_DASHBOARD,
      Permission.VIEW_FILES,
      Permission.UPLOAD_FILES,
      Permission.DOWNLOAD_FILES,
      Permission.VIEW_FOLDERS,
    ],
  },
} as const

export type RoleType = keyof typeof ROLES

// ==================== TIPOS DE RUTAS ====================

export interface RouteMeta {
  title: string
  description?: string
  keywords?: string[]
  ogImage?: string
}

export interface SubRoute {
  path: string
  title: string
  icon?: string
  requiredPermissions?: PermissionType[]
  meta?: RouteMeta
}

export interface RouteConfig {
  path: string
  title: string
  icon: string
  component: string
  showInNav?: boolean
  subRoutes?: SubRoute[]
  requiredPermissions?: PermissionType[]
  meta?: RouteMeta
}

// ==================== CONFIGURACIÓN DE RUTAS ====================

export const routeConfig: RouteConfig[] = [
  {
    path: '/dashboard',
    title: 'Dashboard',
    icon: 'LayoutDashboard',
    component: 'DashboardPage',
    showInNav: true,
    requiredPermissions: [Permission.VIEW_DASHBOARD],
    meta: {
      title: 'Dashboard - FileMeshy',
      description: 'Panel de control principal con estadísticas y métricas del almacenamiento',
      keywords: ['dashboard', 'estadísticas', 'métricas', 'panel de control'],
    },
  },
  {
    path: '/usuarios',
    title: 'Usuarios',
    icon: 'UserCog',
    component: 'UsuariosPage',
    showInNav: true,
    requiredPermissions: [Permission.VIEW_USERS],
    meta: {
      title: 'Usuarios - FileMeshy',
      description: 'Administración de usuarios y permisos del sistema',
      keywords: ['usuarios', 'users', 'permisos', 'roles', 'rbac'],
    },
  },
  {
    path: '/compartido-conmigo',
    title: 'Compartido conmigo',
    icon: 'Share2',
    component: 'SharedWithMePage',
    showInNav: true,
    requiredPermissions: [Permission.VIEW_FILES],
    meta: {
      title: 'Compartido conmigo - FileMeshy',
      description: 'Archivos y carpetas compartidos directamente con tu usuario',
      keywords: ['compartido', 'shares', 'compartir', 'archivos'],
    },
  },
  {
    path: '/cuotas-almacenamiento',
    title: 'Cuotas de Almacenamiento',
    icon: 'HardDrive',
    component: 'StorageQuotasPage',
    showInNav: true,
    requiredPermissions: [Permission.VIEW_STORAGE_QUOTAS],
    meta: {
      title: 'Cuotas de Almacenamiento - FileMeshy',
      description: 'Administración del límite de almacenamiento por usuario',
      keywords: ['cuotas', 'almacenamiento', 'storage', 'límite', 'disco'],
    },
  },
  {
    path: '/configuracion',
    title: 'Configuración',
    icon: 'Settings',
    component: 'ConfiguracionPage',
    showInNav: true,
    requiredPermissions: [Permission.VIEW_SETTINGS],
    meta: {
      title: 'Configuración - FileMeshy',
      description: 'Configuración y ajustes del sistema',
      keywords: ['configuración', 'settings', 'ajustes', 'preferencias'],
    },
  },
  {
    path: '/copias-seguridad',
    title: 'Copias de Seguridad',
    icon: 'DatabaseBackup',
    component: 'BackupsPage',
    showInNav: true,
    requiredPermissions: [Permission.VIEW_BACKUPS],
    meta: {
      title: 'Copias de Seguridad - FileMeshy',
      description: 'Historial y ejecución manual de backups de Postgres y MinIO',
      keywords: ['backups', 'copias de seguridad', 'postgres', 'minio', 'respaldo'],
    },
  },
]

// ==================== FUNCIONES HELPER ====================

/**
 * Verifica si un usuario tiene al menos uno de los permisos requeridos
 */
export const hasPermission = (
  requiredPermissions: PermissionType[],
  userPermissions: PermissionType[]
): boolean => {
  if (!requiredPermissions || requiredPermissions.length === 0) {
    return true
  }

  if (userPermissions.includes(Permission.FULL_ACCESS)) {
    return true
  }

  return requiredPermissions.some((permission) => userPermissions.includes(permission))
}

/**
 * Verifica si un usuario tiene acceso a una ruta específica
 */
export const hasRouteAccess = (path: string, userPermissions: PermissionType[]): boolean => {
  const route = routeConfig.find((r) => r.path === path)

  if (!route) {
    return false
  }

  if (!route.requiredPermissions || route.requiredPermissions.length === 0) {
    return true
  }

  return hasPermission(route.requiredPermissions, userPermissions)
}

/**
 * Filtra las rutas de navegación según los permisos del usuario
 */
export const getAccessibleRoutes = (userPermissions: PermissionType[]): RouteConfig[] => {
  return routeConfig.filter((route) => {
    if (!route.showInNav) {
      return false
    }

    return hasRouteAccess(route.path, userPermissions)
  })
}

/**
 * Obtiene los permisos de un rol específico
 */
export const getPermissionsByRole = (role: keyof typeof ROLES): PermissionType[] => {
  return ROLES[role]?.permissions ? [...ROLES[role].permissions] : []
}

/**
 * Combina múltiples roles en un array único de permisos
 */
export const combineRolePermissions = (roles: (keyof typeof ROLES)[]): PermissionType[] => {
  const allPermissions = roles.flatMap((role) => getPermissionsByRole(role))
  return Array.from(new Set(allPermissions))
}

/**
 * Obtiene una ruta por su path
 */
export const getRouteByPath = (path: string): RouteConfig | undefined => {
  return routeConfig.find((route) => route.path === path)
}

/**
 * Obtiene las rutas que se muestran en navegación
 */
export const getNavigationRoutes = (): RouteConfig[] => {
  return routeConfig.filter((route) => route.showInNav)
}

// ==================== RUTAS PÚBLICAS ====================

export const publicRoutes = [
  {
    path: '/login',
    component: 'Login',
  },
  {
    path: '/reset-password',
    component: 'ResetPassword',
  },
]

// Ruta por defecto
export const defaultRoute = '/dashboard'
