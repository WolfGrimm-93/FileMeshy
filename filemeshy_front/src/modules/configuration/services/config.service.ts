/**
 * Servicio para obtener configuración pública de la app
 * Se llama UNA SOLA VEZ al iniciar la aplicación
 */

import axiosInstance from '@/shared/config/axios'

export interface CompanyConfig {
  business_name: string
  legal_name: string
  logo_path: string | null
  logo_icon_path: string | null
  primary_color: string
  secondary_color: string
  phone: string | null
  email: string | null
  address: string | null
  website: string | null
  city: string | null
  province: string | null
  facebook: string | null
  instagram: string | null
  twitter: string | null
  whatsapp_business: string | null
}

export interface OwnerConfig {
  name: string | null
  email: string | null
  phone: string | null
}

export interface AppConfig {
  version: string
  name: string
  environment: 'development' | 'production'
}

export interface FeaturesConfig {
  two_factor_auth: boolean
  password_reset: boolean
  user_registration: boolean
}

export interface PublicConfig {
  company: CompanyConfig
  owner: OwnerConfig
  app: AppConfig
  features: FeaturesConfig
}

class ConfigService {
  private configCache: PublicConfig | null = null
  private configPromise: Promise<PublicConfig> | null = null

  /**
   * Obtener configuración pública
   * Cachea la configuración para no hacer múltiples peticiones
   */
  async getPublicConfig(): Promise<PublicConfig> {
    // Si ya está en caché, retornar
    if (this.configCache) {
      console.log('📦 Configuración desde caché')
      return this.configCache
    }

    // Si hay una petición en progreso, esperar
    if (this.configPromise) {
      console.log('⏳ Esperando configuración...')
      return this.configPromise
    }

    // Hacer la petición
    this.configPromise = (async () => {
      try {
        console.log('🔄 Cargando configuración pública...')
        const data = await this.fetchWithRetry()

        this.configCache = data
        console.log('✅ Configuración cargada:', this.configCache)

        return this.configCache
      } catch (error) {
        console.error('❌ Error cargando configuración tras reintentos:', error)
        // NO cachear el fallback -- si se cachea acá, cualquier fallo transitorio (ej. el
        // backend reiniciando durante un deploy) deja esta pestaña mostrando datos
        // genéricos (sin marca/logo real) para siempre, hasta que se recargue la página.
        // Al no cachear, la próxima llamada a getPublicConfig() vuelve a intentar contra
        // el backend en vez de repetir este mismo dato malo indefinidamente.
        const fallback: PublicConfig = {
          company: {
            business_name: 'FileMeshy',
            legal_name: 'FileMeshy SRL',
            logo_path: null,
            logo_icon_path: null,
            primary_color: '#3A64D9',
            secondary_color: '#6552E0',
            phone: null,
            email: null,
            address: null,
            website: null,
            city: null,
            province: null,
            facebook: null,
            instagram: null,
            twitter: null,
            whatsapp_business: null,
          },
          owner: {
            name: null,
            email: null,
            phone: null,
          },
          app: {
            version: '1.0.0',
            name: 'FileMeshy',
            environment: 'production'
          },
          features: {
            two_factor_auth: false,
            password_reset: true,
            user_registration: false,
          },
        }
        return fallback
      } finally {
        this.configPromise = null
      }
    })()

    return this.configPromise
  }

  /**
   * Reintenta GET /public/config con backoff corto antes de resignarse al fallback --
   * absorbe la ventana típica de un contenedor reiniciando durante un deploy, sin que el
   * usuario note nada ni haga falta recargar la página.
   */
  private async fetchWithRetry(): Promise<PublicConfig> {
    const delaysMs = [0, 300, 900]
    let lastError: unknown

    for (const delay of delaysMs) {
      if (delay > 0) {
        await new Promise(resolve => setTimeout(resolve, delay))
      }
      try {
        const response = await axiosInstance.get('/public/config')
        return response.data.data
      } catch (error) {
        lastError = error
      }
    }

    throw lastError
  }

  /**
   * Resetear caché (útil después de cambiar configuración en admin)
   */
  clearCache(): void {
    this.configCache = null
    this.configPromise = null
    console.log('🗑️ Caché de configuración limpiado')
  }
}

export const configService = new ConfigService()
