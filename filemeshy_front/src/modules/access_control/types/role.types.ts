/**
 * Tipos TypeScript para el sistema de roles dinámicos
 */

// Estructura de permisos granulares
export interface RolePermissions {
  files?: string[]
  folders?: string[]
  shares?: string[]
  users?: string[]
  settings?: string[]
  workspace?: string[]
  [key: string]: string[] | undefined
}

// Rol base
export interface Role {
  id: string
  name: string
  display_name: string
  description?: string
  permissions: RolePermissions
  is_system: boolean
  is_active: boolean
  created_by_id?: string
  created_at: string
  updated_at: string
}

// Rol con información adicional para UI
export interface RoleResponse extends Role {
  users_count?: number
  // Conteo real desde role_permissions -- `permissions` (heredado de Role, JSONB
  // legacy) queda siempre vacío, no sirve para contar.
  permissions_count?: number
  can_be_modified?: boolean
  can_be_deleted?: boolean
}

// Para crear un rol
export interface RoleCreate {
  name: string
  display_name: string
  description?: string
  permissions: RolePermissions
  /** ids de permisos reales (role_permissions); se persisten en la misma transacción del alta */
  permission_ids?: string[]
  is_active?: boolean
}

// Para actualizar un rol
export interface RoleUpdate {
  display_name?: string
  description?: string
  permissions?: RolePermissions
  is_active?: boolean
}

// Resumen de rol para selects/dropdowns
export interface RoleSummary {
  id: string
  name: string
  display_name: string
  description?: string
  is_system: boolean
  is_active: boolean
}

// Respuesta paginada de roles
export interface RoleListResponse {
  total: number
  items: RoleResponse[]
  active_count: number
  system_count: number
}

// Para verificar permisos
export interface RolePermissionCheck {
  role_id: string
  resource: string
  action: string
}

export interface RolePermissionCheckResponse {
  has_permission: boolean
  role_id: string
  role_name: string
  resource: string
  action: string
}

// Permisos disponibles por recurso — SOLO FALLBACK.
// La fuente de verdad es GET /permissions/available (tabla `permissions` en BD).
// useAvailablePermissions() carga desde la API; este objeto se usa únicamente
// si la API no está disponible en el momento de renderizar el editor.
// Al agregar permisos al backend, actualizar también aquí para mantener el fallback.
export const AVAILABLE_PERMISSIONS: Record<string, string[]> = {
  dashboard:  ['view'],
  files:      ['view', 'upload', 'download', 'delete', 'rename', 'move'],
  folders:    ['create', 'view', 'delete', 'rename', 'move'],
  shares:     ['create', 'revoke', 'manage'],
  users:      ['view', 'create', 'edit', 'delete', 'manage_roles'],
  settings:   ['view', 'edit_email', 'edit_system'],
  workspace:  ['manage'],
  logs:       ['view'],
  admin:      ['manage'],
  permissions: ['manage'],
}

// Labels en español para los recursos
export const RESOURCE_LABELS: Record<string, string> = {
  dashboard:  'Dashboard',
  files:      'Archivos',
  folders:    'Carpetas',
  shares:     'Compartidos',
  users:      'Usuarios',
  settings:   'Configuración',
  workspace:  'Workspace',
  logs:       'Auditoría',
  admin:      'Administración',
  permissions: 'Permisos',
}

// Labels en español para las acciones
export const ACTION_LABELS: Record<string, string> = {
  view:          'Ver',
  create:        'Crear',
  edit:          'Editar',
  delete:        'Eliminar',
  manage:        'Gestionar (total)',
  upload:        'Subir',
  download:      'Descargar',
  rename:        'Renombrar',
  move:          'Mover',
  revoke:        'Revocar',
  edit_email:    'Configurar email',
  edit_system:   'Editar sistema',
  manage_roles:  'Gestionar roles',
}
