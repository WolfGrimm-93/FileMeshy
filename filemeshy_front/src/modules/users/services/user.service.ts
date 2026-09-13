import axiosInstance from '@/shared/config/axios'

// ===== INTERFACES =====

export interface User {
  id: string
  email: string
  first_name: string
  last_name: string
  phone?: string
  is_active: boolean
  role: string
  role_id?: string
  permissions: string[]
  avatar?: string | null
  theme?: string
  sesiones_activas?: number
  created_at: string
  updated_at?: string
  last_login?: string
}

export interface UserCreate {
  email: string
  first_name: string
  last_name: string
  phone?: string
  password: string
  is_active?: boolean
  role?: string
  role_id?: string
}

export interface UserUpdate {
  email?: string
  first_name?: string
  phone?: string
  last_name?: string
  is_active?: boolean
  password?: string
  role?: string
  role_id?: string
  permissions?: string[]
  avatar?: string | null
}

export interface UserFilters {
  skip?: number
  limit?: number
  search?: string
  role?: string
  is_active?: boolean
}

export interface UsersResponse {
  items: User[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// ===== STATS INTERFACES =====
export interface UserStats {
  total: number
  total_active: number
  total_inactive: number
  roles: Record<string, number>
}

// ===== SESSION INTERFACES =====
export interface UserSession {
  id: string
  user_id: string
  device_name?: string
  device_type?: string
  ip_address?: string
  user_agent?: string
  created_at: string
  last_activity: string
  expires_at: string
  is_active: boolean
}

export interface UserSessionsResponse {
  items: UserSession[]
  total: number
}

// ===== SERVICE =====
class UserService {
  private basePath = '/users'

  /**
   * Obtener estadísticas globales de usuarios
   */
  async getStats(): Promise<UserStats> {
    const response = await axiosInstance.get<UserStats>(`${this.basePath}/stats`)
    return response.data
  }

  /**
   * Obtener lista de usuarios con paginación y filtros
   */
  async getUsers(params?: UserFilters): Promise<UsersResponse> {
    const response = await axiosInstance.get<UsersResponse>(this.basePath, { params })
    return response.data
  }

  /**
   * Obtener un usuario por ID
   */
  async getUser(id: string): Promise<User> {
    const response = await axiosInstance.get<User>(`${this.basePath}/${id}`)
    return response.data
  }

  /**
   * Crear un nuevo usuario
   */
  async createUser(data: UserCreate): Promise<User> {
    const response = await axiosInstance.post<User>(this.basePath, data)
    return response.data
  }

  /**
   * Actualizar un usuario existente
   */
  async updateUser(id: string, data: UserUpdate): Promise<User> {
    const response = await axiosInstance.put<User>(`${this.basePath}/${id}`, data)
    return response.data
  }

  /**
   * Eliminar un usuario
   */
  async deleteUser(id: string): Promise<void> {
    await axiosInstance.delete(`${this.basePath}/${id}`)
  }

  /**
   * Obtener el usuario actual (del token)
   */
  async getCurrentUser(): Promise<User> {
    const response = await axiosInstance.get<User>('/auth/me')
    return response.data
  }

  /**
   * Obtener sesiones activas de un usuario
   */
  async getUserSessions(userId: string, includeExpired: boolean = false): Promise<UserSessionsResponse> {
    const response = await axiosInstance.get<UserSessionsResponse>(
      `${this.basePath}/${userId}/sessions`,
      { params: { include_expired: includeExpired } }
    )
    return response.data
  }

  /**
   * Cerrar una sesión específica de un usuario
   */
  async revokeUserSession(userId: string, sessionId: string): Promise<void> {
    await axiosInstance.delete(`${this.basePath}/${userId}/sessions/${sessionId}`)
  }

  /**
   * Cerrar todas las sesiones de un usuario
   */
  async revokeAllUserSessions(userId: string): Promise<void> {
    await axiosInstance.delete(`${this.basePath}/${userId}/sessions`)
  }

  async uploadAvatar(userId: string, file: File): Promise<User> {
    const form = new FormData()
    form.append('file', file)
    const response = await axiosInstance.post<User>(`${this.basePath}/${userId}/avatar`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  }
}

export const userService = new UserService()
