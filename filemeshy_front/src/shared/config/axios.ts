/**
 * Configuración de Axios para peticiones HTTP con OAuth 2.0
 * 
 * Características:
 * - withCredentials: true para enviar/recibir cookies httpOnly
 * - Auto-refresh en 401 (token expirado)
 * - Token rotation automático
 * - Interceptores de request y response
 */
import axios, { type AxiosInstance, type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { env, getApiUrl, getTenantSlug } from './env'

// Crear instancia de axios SIN baseURL fija — se inyecta dinámicamente en el
// interceptor de request para que initConfig() pueda cambiar la URL antes de
// que se haga la primera petición.
const axiosInstance: AxiosInstance = axios.create({
  timeout: env.apiTimeout,
  withCredentials: true, // ✅ Enviar/recibir cookies httpOnly automáticamente
  headers: {
    'Content-Type': 'application/json; charset=utf-8', // ✅ Especificar charset UTF-8
    'Accept': 'application/json; charset=utf-8',       // ✅ Especificar charset UTF-8
  },
})

// CSRF (doble-submit cookie, ver filemeshy_back/app/middleware/csrf.py) — la
// cookie filemeshy_csrf_token no es httpOnly a propósito, para que el
// frontend la lea acá y la reenvíe como header. El backend solo compara
// cookie == header.
function getCsrfTokenFromCookie(): string | null {
  const match = document.cookie.match(/(?:^|; )filemeshy_csrf_token=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : null
}

const METODOS_MUTABLES = new Set(['post', 'put', 'patch', 'delete'])

// Request interceptor - Inyectar baseURL dinámica + token
axiosInstance.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    // Siempre leer la URL activa (la calcula initConfig contra el dominio actual)
    if (!config.baseURL) {
      config.baseURL = getApiUrl()
    }

    // Multi-tenancy (fase 2): solo se manda si hay un tenant elegido (login,
    // lab de tenants). En toda instalacion normal queda vacio -- no-op.
    const tenantSlug = getTenantSlug()
    if (tenantSlug && config.headers) {
      config.headers['X-Tenant-Slug'] = tenantSlug
    }

    // Cambiar de usuario (sesiones apiladas, ver auth.service.ts): le dice al
    // backend qué cookie de refresh mirar -- refresh_token para el slot 0 (la
    // sesión base, sin cambios) o refresh_token_slot_{n} para cada sesión
    // pausada encima. El header NUNCA autoriza nada por sí solo (solo enruta
    // qué cookie leer); la identidad la sigue probando el JWT firmado dentro
    // de esa cookie httpOnly. Se manda en TODAS las requests, incluidas las
    // públicas (login/logout necesitan saber a qué slot afecta la operación),
    // por eso el import de authService se hace acá arriba y no solo dentro
    // del bloque de Authorization más abajo.
    let authServiceModule: typeof import('@/modules/auth/services/auth.service') | null = null
    try {
      authServiceModule = await import('@/modules/auth/services/auth.service')
      if (config.headers) {
        config.headers['X-Session-Slot'] = String(authServiceModule.authService.getActiveSlot())
      }
    } catch (error) {
      if (env.isDev) {
        console.warn('⚠️  No se pudo obtener authService para X-Session-Slot:', error)
      }
    }

    // CSRF: solo en métodos que mutan estado — antes de tener sesión (login)
    // no existe la cookie todavía, así que esto es no-op hasta el primer login.
    if (config.method && METODOS_MUTABLES.has(config.method) && config.headers) {
      const csrfToken = getCsrfTokenFromCookie()
      if (csrfToken) {
        config.headers['X-XSRF-TOKEN'] = csrfToken
      }
    }

    // ✅ Rutas públicas que NO deben tener Authorization header
    const publicRoutes = [
      '/public/',                    // /api/v1/public/*
      '/auth/login',                 // POST /auth/login
      '/auth/register',              // POST /auth/register
      '/auth/password-reset/request', // POST /auth/password-reset/request
      '/auth/password-reset/verify',  // POST /auth/password-reset/verify
      '/auth/password-reset/confirm', // POST /auth/password-reset/confirm
      '/auth/logout',                // POST /auth/logout (cierra sesión)
      '/auth/turnstile-config'       // GET /auth/turnstile-config (config pública)
    ]

    const isPublicRoute = publicRoutes.some(route => config.url?.includes(route))

    if (!isPublicRoute) {
      // Reusa el mismo import de authService de arriba (X-Session-Slot) --
      // evita una segunda import dinámica para lo mismo.
      try {
        const token = authServiceModule?.authService.getAccessToken()

        // Solo adjuntar si el token existe Y no está vacío
        if (token && token.trim() && config.headers) {
          config.headers.Authorization = `Bearer ${token}`
        }
      } catch (error) {
        // Ignorar error si no se puede obtener el token
        if (env.isDev) {
          console.warn('⚠️  No se pudo obtener token:', error)
        }
      }
    }
    
    // Logs de HTTP deshabilitados — activar solo para debug puntual
    // if (env.isDev && !isPublicRoute) {
    //   console.log('📤 Request:', config.method?.toUpperCase(), config.url)
    // }
    
    return config
  },
  (error) => {
    if (env.isDev) {
      console.error('❌ Request Error:', error)
    }
    return Promise.reject(error)
  }
)

// Response interceptor - Manejar respuestas y errores (auto-refresh en 401)
axiosInstance.interceptors.response.use(
  (response) => {
    // Log en desarrollo
    // Log de respuestas deshabilitado — activar solo para debug puntual
    // if (env.isDev) console.log('📥 Response:', response.status, response.config.url)
    
    return response
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined
    
    if (!originalRequest) {
      return Promise.reject(error)
    }
    
    // ✅ Rutas públicas que NUNCA deben intentar refresh
    const publicRoutes = [
      '/public/',
      '/auth/login',
      '/auth/register',
      '/auth/password-reset/request',
      '/auth/password-reset/verify',
      '/auth/password-reset/confirm',
      '/auth/logout',
      '/auth/refresh' // el propio refresh nunca debe reintentar refresh (recursión)
    ]
    const isPublicRoute = publicRoutes.some(route => originalRequest.url?.includes(route))
    
    // ❌ En rutas públicas, NUNCA intentar refresh - rechazar error directamente
    if (isPublicRoute) {
      if (env.isDev) {
        console.debug('📥 Public route, no refresh:', error.response?.status, originalRequest.url)
      }
      return Promise.reject(error)
    }
    
    // 🚫 403 FORBIDDEN - NO intentar refresh, es un error de permisos
    // El usuario está autenticado pero NO tiene permiso para este recurso
    if (error.response?.status === 403) {
      if (env.isDev) {
        console.debug('🚫 403 Forbidden - No autorizado para acceder a este recurso:', originalRequest.url)
      }
      // NO reintentar, NO hacer refresh, solo rechazar
      return Promise.reject(error)
    }
    
    // Si el error es 401 (token expirado) y no hemos reintentado
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      if (env.isDev) {
        console.debug('🔄 Token expirado, iniciando refresh...')
      }

      try {
        // Importar authService dinámicamente para evitar circular dependency.
        // refreshToken() dedupea internamente (refreshPromise): cualquier
        // cantidad de requests 401 simultáneos comparten la MISMA llamada de
        // red real en vez de disparar cada uno su propio POST /auth/refresh
        // (evita la carrera contra la rotación de un solo uso del token).
        const { authService } = await import('@/modules/auth/services/auth.service')
        const { access_token: newAccessToken } = await authService.refreshToken()

        // Actualizar el header de la request original
        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${newAccessToken}`
        }

        if (env.isDev) {
          console.debug('✅ Token refrescado exitosamente')
        }

        // Reintentar la request original con el nuevo token
        return axiosInstance(originalRequest)
      } catch (refreshError) {
        if (env.isDev) {
          console.error('❌ Error en refresh:', refreshError)
        }

        // Solo hacer logout si el servidor rechazó el refresh (401/403)
        // En errores de red (timeout, sin conexión) NO cerrar sesión
        const refreshAxiosError = refreshError as AxiosError
        const hasServerResponse = !!refreshAxiosError?.response

        if (hasServerResponse) {
          const { authService } = await import('@/modules/auth/services/auth.service')
          // Capturar el slot ANTES de discardPausedSessions() -- después de
          // eso getActiveSlot() ya vuelve a dar 0 siempre.
          const failedSlot = authService.getActiveSlot()
          authService.clearAutoRefresh()
          authService.setAccessToken(null)
          // Si había sesiones pausadas por "Cambiar de usuario", no queda
          // forma de volver a ellas después de este logout forzado -- evita
          // que sus tokens queden huérfanos en memoria (auditoría).
          authService.discardPausedSessions()

          // Limpiar cookie httpOnly del refresh_token via el backend -- SOLO
          // la del slot que de verdad falló (scope=current). Sin esto, el
          // default scope=all del backend cierra también cualquier sesión
          // pausada que todavía fuera válida debajo (hallazgo de auditoría:
          // este logout forzado no debe destruir sesiones ajenas a la que
          // realmente falló refrescar).
          try {
            await axios.post(`${getApiUrl()}/auth/logout`, {}, {
              withCredentials: true,
              params: { scope: 'current' },
              headers: {
                'X-Session-Slot': String(failedSlot),
                ...(getTenantSlug() ? { 'X-Tenant-Slug': getTenantSlug() } : {}),
              },
            })
          } catch {
            // Ignorar error de logout - lo importante es limpiar el estado local
          }

          const { useAuthStore } = await import('@/modules/auth/store/authStore')
          useAuthStore.getState().logout()
        }

        return Promise.reject(refreshError)
      }
    }
    
    // Log en desarrollo
    if (env.isDev) {
      console.error('❌ Response Error:', error.response?.status, error.config?.url)
    }
    
    return Promise.reject(error)
  }
)

export default axiosInstance

// Helper types
export interface ApiResponse<T = unknown> {
  status: string
  message?: string
  data: T
}

export interface ApiError {
  message: string
  errors?: Record<string, string[]>
  statusCode?: number
}
