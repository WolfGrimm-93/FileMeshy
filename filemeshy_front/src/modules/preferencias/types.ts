/**
 * TIPOS Y E INTERFACES - MÓDULO DE PREFERENCIAS DE USUARIO
 * Define los tipos para Mi Perfil, Seguridad, Apariencia y Notificaciones
 */

// ==================== MI PERFIL ====================
export interface UserProfile {
  id: number
  email: string
  first_name: string
  last_name: string
  phone?: string
  avatar?: string
  role: string
  role_id: number
  is_active: boolean
  created_at: string
  updated_at?: string
  last_login?: string
}

export interface UserProfileUpdate {
  first_name?: string
  last_name?: string
  phone?: string
  email?: string
  avatar?: string
}

// ==================== SEGURIDAD ====================
export interface PasswordChange {
  current_password: string
  new_password: string
  confirm_password: string
}

export interface SecurityPolicies {
  id: string
  min_password_length: number
  require_uppercase: boolean
  require_lowercase: boolean
  require_numbers: boolean
  require_special_chars: boolean
  password_expiration_days: number
  password_history: number
  session_timeout_minutes: number
  max_session_duration_hours: number
  allow_concurrent_sessions: boolean
  max_concurrent_sessions?: number
  enable_account_lockout: boolean
  max_login_attempts: number
  lockout_duration_minutes: number
  enforce_2fa: boolean
  enforce_2fa_for_admins: boolean
  log_login_attempts: boolean
  log_password_changes: boolean
  log_permission_changes: boolean
  enable_ip_whitelist: boolean
  allowed_ips?: string[]
  enable_geo_blocking: boolean
  allowed_countries?: string[]
  notify_on_new_login: boolean
  notify_on_password_change: boolean
  notify_on_suspicious_activity: boolean
  created_at: string
  updated_at: string
  updated_by?: string
}

// ==================== APARIENCIA ====================
export interface UserPreferences {
  id: string
  user_id: string
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
  created_at: string
  updated_at?: string
}

export interface UserPreferencesUpdate {
  theme?: 'light' | 'dark' | 'auto'
  language?: string
  font_size?: string
  date_format?: string
  time_format?: string
  currency?: string
  dashboard_layout?: unknown
  email_notifications?: boolean
  system_notifications?: boolean
  rows_per_page?: number
  auto_refresh?: boolean
  auto_refresh_interval?: number
}

// ==================== NOTIFICACIONES ====================
export interface NotificationPreferences {
  email_notifications: boolean
  system_notifications: boolean
  notification_types?: {
    sales?: boolean
    inventory?: boolean
    payments?: boolean
    system?: boolean
  }
  daily_summary: boolean
  weekly_summary: boolean
  monthly_summary: boolean
}

// ==================== SESIONES ACTIVAS ====================
export interface UserSession {
  id: number
  user_id: number
  device_name?: string
  device_type?: string
  ip_address?: string
  user_agent?: string
  is_active: boolean
  created_at: string
  last_activity: string
  expires_at: string
}
