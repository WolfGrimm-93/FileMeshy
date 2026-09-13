/**
 * Servicio de preferencias de usuario
 * Gestiona las preferencias almacenadas en el backend
 */
import axiosInstance from '@/shared/config/axios'

export interface UserPreferences {
  theme: 'light' | 'dark' | 'auto'
  language: string
  font_size: string
  date_format: string
  time_format: string
  currency: string
  dashboard_layout?: unknown
  active_kpis?: unknown
  default_dashboard_period?: string
  real_time_updates: boolean
  update_interval?: number
  email_notifications: boolean
  system_notifications: boolean
  notification_types?: unknown
  daily_summary: boolean
  weekly_summary: boolean
  monthly_summary: boolean
  rows_per_page: number
  default_view?: string
  auto_refresh: boolean
  auto_refresh_interval?: number
  export_format?: string
  include_charts: boolean
  include_summary: boolean
  custom_preferences?: unknown
}

class UserPreferencesService {
  /**
   * Obtener preferencias del usuario actual
   */
  async getMyPreferences(): Promise<UserPreferences> {
    const response = await axiosInstance.get('/config/preferences/my-preferences')
    return response.data.data ?? response.data
  }

  /**
   * Actualizar preferencias del usuario
   */
  async updateMyPreferences(preferences: Partial<UserPreferences>): Promise<UserPreferences> {
    const response = await axiosInstance.put('/config/preferences/my-preferences', preferences)
    return response.data.data
  }

}

export const userPreferencesService = new UserPreferencesService()
