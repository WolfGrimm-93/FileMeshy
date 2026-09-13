/**
 * Tipos para el módulo de gestión de usuarios
 * 
 * Nota: Para el tipo User del backend, importar desde:
 * @/modules/users/services/user.service
 */

export interface UserFormData {
  first_name: string
  last_name: string
  email: string
  phone: string
  role: string
  role_id?: string
  is_active: boolean
  password?: string
  confirmarPassword?: string
}

export interface UserStats {
  totalUsuarios: number
  usuariosActivos: number
  usuariosInactivos: number
  ultimosAccesos: number
}
