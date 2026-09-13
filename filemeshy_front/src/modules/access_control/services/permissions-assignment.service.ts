/**
 * Servicio para la asignación rol<->permiso (tabla role_permissions).
 *
 * Distinto de useAvailablePermissions()/GET /permissions/available (catálogo
 * agrupado por recurso, sin IDs) -- este servicio trabaja con los permission_id
 * reales necesarios para asignar/quitar permisos de un rol.
 */
import axiosInstance from '@/shared/config/axios'
import type { RolePermissions } from '../types/role.types'

export interface PermissionCatalogItem {
  id: string
  permission_code: string
  permission_name: string
  permission_category: string
  resource: string
  description?: string | null
  is_system: boolean
  is_active: boolean
}

export interface RolePermissionsResponse {
  role_id: string
  role_name: string
  assigned_permission_ids: string[]
  catalog: PermissionCatalogItem[]
}

/** Convierte los `permission_id` asignados (tabla role_permissions) al shape
 * {resource: [actions]} que consume RolePermissionsEditor. */
export function idsToPermissionsDict(assignedIds: string[], catalog: PermissionCatalogItem[]): RolePermissions {
  const byId = new Map(catalog.map((p) => [p.id, p]))
  const dict: RolePermissions = {}
  for (const id of assignedIds) {
    const perm = byId.get(id)
    if (!perm) continue
    const [resource, action] = perm.permission_code.split('.', 2)
    if (!resource || !action) continue
    if (!dict[resource]) dict[resource] = []
    dict[resource]!.push(action)
  }
  return dict
}

/** Inverso de idsToPermissionsDict: del shape {resource: [actions]} a los
 * `permission_id` reales que hay que mandarle a PUT /roles/{id}/permissions. */
export function permissionsDictToIds(dict: RolePermissions, catalog: PermissionCatalogItem[]): string[] {
  const byCode = new Map(catalog.map((p) => [p.permission_code, p.id]))
  const ids: string[] = []
  for (const [resource, actions] of Object.entries(dict)) {
    for (const action of actions || []) {
      const id = byCode.get(`${resource}.${action}`)
      if (id) ids.push(id)
    }
  }
  return ids
}

export const permissionsAssignmentService = {
  async getForRole(roleId: string): Promise<RolePermissionsResponse> {
    const response = await axiosInstance.get<RolePermissionsResponse>(`/roles/${roleId}/permissions`)
    return response.data
  },

  async updateForRole(roleId: string, permissionIds: string[]): Promise<RolePermissionsResponse> {
    const response = await axiosInstance.put<RolePermissionsResponse>(`/roles/${roleId}/permissions`, {
      permission_ids: permissionIds,
    })
    return response.data
  },
}
