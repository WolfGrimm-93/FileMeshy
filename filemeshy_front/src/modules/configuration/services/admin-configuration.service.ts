/**
 * Servicio API para Configuración Administrativa
 * Conecta con el backend para gestionar configuraciones del sistema
 * Requiere permisos de administrador
 */

import axiosInstance from '@/shared/config/axios'

// ============================================================================
// INTERFACES - CLOUDFLARE TURNSTILE
// ============================================================================

export interface TurnstileConfig {
  enabled: boolean
  site_key: string
  secret_key_configured: boolean
}

export interface TurnstileConfigUpdate {
  enabled: boolean
  site_key: string
  secret_key?: string
}

// ============================================================================
// SERVICIO - ADMIN CONFIGURATION
// ============================================================================

class AdminConfigurationService {
  // === EMAIL / SMTP ===

  async getEmailConfig(): Promise<EmailConfig> {
    const response = await axiosInstance.get<{ data: EmailConfig }>('/admin/config/email')
    return response.data.data
  }

  async updateEmailConfig(data: EmailConfigUpdate): Promise<void> {
    await axiosInstance.put('/admin/config/email', data)
  }

  async testSmtpConnection(): Promise<{ message: string; status: string }> {
    const response = await axiosInstance.post<{ message: string; status: string }>('/admin/config/smtp/test')
    return response.data
  }

  async getNotificationTypes(): Promise<NotificationTypesConfig> {
    const response = await axiosInstance.get<{ data: NotificationTypesConfig }>('/admin/config/notification-types')
    return response.data.data
  }

  async updateNotificationTypes(types: NotificationTypesConfig): Promise<void> {
    await axiosInstance.put('/admin/config/notification-types', { types })
  }

  // === TURNSTILE ===

  async getTurnstileConfig(): Promise<TurnstileConfig> {
    const response = await axiosInstance.get<TurnstileConfig>('/admin/configuration/turnstile')
    return response.data
  }

  async updateTurnstileConfig(data: TurnstileConfigUpdate): Promise<void> {
    await axiosInstance.put('/admin/configuration/turnstile', data)
  }

  // === R5: VERSIÓN GLOBAL DE CONFIG (polling multi-terminal) ===

  async getConfigVersion(): Promise<number> {
    const response = await axiosInstance.get<{ version: number }>('/config/version')
    return response.data.version
  }
}

// ============================================================================
// INTERFACES - CONFIGURACIÓN DE EMAIL / SMTP
// ============================================================================

export type EmailMethod = 'smtp'

export interface NotificationTypeSettings {
  email: boolean
  sistema: boolean
}

export type NotificationTypesConfig = Record<string, NotificationTypeSettings>

// Vacío hasta que existan eventos reales del dominio de archivos que notificar
// (ej. "archivo compartido", "cuota de almacenamiento al límite").
export const DEFAULT_NOTIF_TYPES_CONFIG: NotificationTypesConfig = {}

export interface EmailConfig {
  account_email: string
  account_username: string
  smtp_host: string
  smtp_username: string
  smtp_password: string  // '****' cuando se carga, valor real al guardar
  smtp_insecure_port: number
  smtp_secure_port: number
  domain_name?: string
  display_name?: string
  email_method?: EmailMethod
}

export interface EmailConfigUpdate {
  account_email?: string
  account_username?: string
  smtp_host?: string
  smtp_username?: string
  smtp_password?: string
  smtp_insecure_port?: number
  smtp_secure_port?: number
  domain_name?: string
  display_name?: string
  email_method?: EmailMethod
}

// Exportar instancia única
export const adminConfigurationService = new AdminConfigurationService()

// Export default para compatibilidad
export default adminConfigurationService
