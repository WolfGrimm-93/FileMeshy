/**
 * Servicio para las excepciones individuales de permiso por usuario
 * (tabla user_permission_overrides) -- capa aditiva sobre role_permissions.
 *
 * Distinto de permissions-assignment.service.ts (que asigna permisos a un ROL):
 * este trabaja sobre un USUARIO puntual, agregando/quitando permisos respecto de
 * lo que le da su rol, sin cambiarle el rol ni perder la excepcion cuando se edite
 * el set de permisos de ese rol desde la pantalla de Gestión de Permisos.
 */
import axiosInstance from '@/shared/config/axios'
import type { PermissionCatalogItem } from './permissions-assignment.service'

export interface UserPermissionOverridesResponse {
  user_id: string
  role_id: string | null
  role_permission_ids: string[]
  grant_ids: string[]
  revoke_ids: string[]
  catalog: PermissionCatalogItem[]
}

export const userPermissionOverridesService = {
  async getForUser(userId: string): Promise<UserPermissionOverridesResponse> {
    const response = await axiosInstance.get<UserPermissionOverridesResponse>(`/users/${userId}/permission-overrides`)
    return response.data
  },

  async updateForUser(userId: string, grantIds: string[], revokeIds: string[]): Promise<UserPermissionOverridesResponse> {
    const response = await axiosInstance.put<UserPermissionOverridesResponse>(`/users/${userId}/permission-overrides`, {
      grant_ids: grantIds,
      revoke_ids: revokeIds,
    })
    return response.data
  },
}
