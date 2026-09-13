/**
 * Servicio para gestión de roles dinámicos
 */
import axiosInstance from '@/shared/config/axios'
import type {
  RoleResponse,
  RoleCreate,
  RoleUpdate,
  RoleSummary,
  RoleListResponse,
  RolePermissionCheck,
  RolePermissionCheckResponse
} from '../types/role.types'

const BASE_URL = '/roles'

export const rolesService = {
  /**
   * Listar todos los roles (requiere ADMIN o SUPER_ADMIN)
   * 
   * Nota: Este endpoint retorna RoleListResponse directamente, no envuelto en { data: ... }
   */
  async list(params?: {
    skip?: number
    limit?: number
    active_only?: boolean
    include_system?: boolean
  }): Promise<RoleListResponse> {
    const queryParams = new URLSearchParams()
    if (params?.skip !== undefined) queryParams.append('skip', params.skip.toString())
    if (params?.limit !== undefined) queryParams.append('limit', params.limit.toString())
    if (params?.active_only !== undefined)
      queryParams.append('active_only', params.active_only.toString())
    if (params?.include_system !== undefined)
      queryParams.append('include_system', params.include_system.toString())

    const url = queryParams.toString() ? `${BASE_URL}?${queryParams}` : BASE_URL
    const response = await axiosInstance.get<RoleListResponse>(url)
    return response.data
  },

  /**
   * Obtener resumen de roles para selects/dropdowns
   * (Todos los usuarios autenticados pueden acceder)
   * 
   * Nota: Este endpoint retorna array directamente, no envuelto en { data: ... }
   */
  async getSummary(activeOnly: boolean = true): Promise<RoleSummary[]> {
    const url = `${BASE_URL}/summary?active_only=${activeOnly}`
    const response = await axiosInstance.get<RoleSummary[]>(url)
    return response.data
  },

  /**
   * Obtener rol por ID
   */
  async getById(roleId: string): Promise<RoleResponse> {
    const response = await axiosInstance.get<RoleResponse>(`${BASE_URL}/${roleId}`)
    return response.data
  },

  /**
   * Crear nuevo rol (solo SUPER_ADMIN)
   */
  async create(roleData: RoleCreate): Promise<RoleResponse> {
    const response = await axiosInstance.post<RoleResponse>(BASE_URL, roleData)
    return response.data
  },

  /**
   * Actualizar rol (solo SUPER_ADMIN)
   * No se pueden modificar roles del sistema
   */
  async update(roleId: string, roleData: RoleUpdate): Promise<RoleResponse> {
    const response = await axiosInstance.put<RoleResponse>(`${BASE_URL}/${roleId}`, roleData)
    return response.data
  },

  /**
   * Eliminar rol (solo SUPER_ADMIN)
   * No se pueden eliminar roles del sistema ni roles con usuarios asignados
   */
  async delete(roleId: string): Promise<void> {
    await axiosInstance.delete(`${BASE_URL}/${roleId}`)
  },

  /**
   * Verificar si un rol tiene un permiso específico
   */
  async checkPermission(
    check: RolePermissionCheck
  ): Promise<RolePermissionCheckResponse> {
    const response = await axiosInstance.post<RolePermissionCheckResponse>(`${BASE_URL}/check-permission`, check)
    return response.data
  },

  /**
   * Validar que un nombre de rol sea válido (mayúsculas, sin espacios)
   */
  validateRoleName(name: string): { valid: boolean; error?: string } {
    if (!name) {
      return { valid: false, error: 'El nombre es requerido' }
    }

    if (name !== name.toUpperCase()) {
      return { valid: false, error: 'El nombre debe estar en MAYÚSCULAS' }
    }

    if (!/^[A-Z_]+$/.test(name)) {
      return {
        valid: false,
        error: 'El nombre solo puede contener letras mayúsculas y guiones bajos'
      }
    }

    if (name.length < 3 || name.length > 50) {
      return { valid: false, error: 'El nombre debe tener entre 3 y 50 caracteres' }
    }

    return { valid: true }
  },

  /**
   * Verificar si un rol puede ser modificado.
   * La restricción de roles del sistema se valida en el backend (solo SUPER_ADMIN puede editarlos).
   */
  canModifyRole(_role: RoleResponse): boolean {
    return true
  },

  /**
   * Verificar si un rol puede ser eliminado
   */
  canDeleteRole(role: RoleResponse): boolean {
    if (role.is_system) return false
    if (role.users_count && role.users_count > 0) return false
    return role.can_be_deleted ?? true
  }
}
