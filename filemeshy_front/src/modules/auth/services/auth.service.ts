/**
 * Servicio de autenticación con OAuth 2.0
 * 
 * Características de seguridad:
 * - Access token en memoria (protección contra XSS)
 * - Refresh token en httpOnly cookie (protección contra XSS y CSRF)
 * - Auto-refresh automático 5 minutos antes de expirar
 * - Token rotation en cada refresh
 */
import axios from 'axios'
import axiosInstance from '@/shared/config/axios'
import { getApiUrl, getTenantSlug } from '@/shared/config/env'
import { cleanupAllExceptSettings } from '@/shared/utils/cleanup-storage'

export interface LoginCredentials {
  email: string
  password: string
  remember_me?: boolean
  turnstile_token?: string | null
}

export interface TurnstileConfig {
  enabled: boolean
  site_key: string
}

export interface RegisterData {
  first_name: string  // Backend espera first_name
  last_name: string   // Backend espera last_name
  email: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: User
}

export interface TwoFactorLoginResponse {
  requires_2fa: true
  pre_auth_token: string
}

export type LoginResult = LoginResponse | TwoFactorLoginResponse

export interface TwoFactorSetupData {
  qr_code: string       // data:image/png;base64,...
  secret: string        // para entrada manual
  backup_codes: string[]
}

export interface TwoFactorStatus {
  enabled: boolean
  backup_codes_remaining: number
}

export interface RefreshResponse {
  access_token: string
  token_type: string
}

// Cambio de contraseña estando logueado (distinto del flujo de "olvidé mi
// contraseña" -- ver password-reset.service.ts). Migrado desde
// modules/preferencias/services/security.service.ts: no duplicaba lógica de
// este archivo, era funcionalidad real sin hogar.
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

export interface User {
  id: string  // UUID v7 (Backend usa UUID, no integer)
  first_name: string
  last_name: string
  email: string
  role: string
  permissions: string[]
  avatar?: string
  theme?: 'light' | 'dark' | 'auto'
}

// Constantes de tiempo
const ACCESS_TOKEN_LIFETIME = 30 * 60 * 1000 // 30 minutos
const AUTO_REFRESH_BEFORE = 5 * 60 * 1000 // 5 minutos antes de expirar
const AUTO_REFRESH_INTERVAL = ACCESS_TOKEN_LIFETIME - AUTO_REFRESH_BEFORE // 25 minutos

// Tope de sesiones apiladas por "Cambiar de usuario" -- DEBE coincidir con
// MAX_SESSION_SLOTS del backend (ver AUDITORIA_disenos.md). Slots válidos:
// 0 (sesión base) hasta MAX_SESSION_SLOTS - 1 (última pausada admitida). El
// backend rechaza con 400 cualquier slot fuera de ese rango -- este límite
// del lado del frontend es solo para dar un error claro en la UI antes de
// llegar a pegarle a /auth/login con un slot que el backend va a rechazar.
export const MAX_SESSION_SLOTS = 4

interface PausedTokens {
  accessToken: string | null
}

class AuthService {
  // Token en memoria (NO en localStorage por seguridad XSS)
  private accessToken: string | null = null
  // Pila de tokens pausados por "cambiar de usuario" (ver pauseCurrentSession/
  // resumePreviousSession) -- cada entrada es la sesion completa de un usuario
  // que quedo en pausa debajo del que esta activo ahora. El objeto User de
  // cada uno vive en authStore.pausedUsers (useAuth.ts los mantiene en sync),
  // no aca -- este servicio solo conoce tokens. Su longitud ES el slot activo
  // (ver getActiveSlot()).
  //
  // Decisión (post-auditoría, cookies por slot): esto sigue cacheando el
  // accessToken en memoria para web exactamente como antes -- el esquema de
  // cookies por slot resuelve la PERSISTENCIA del refresh token (que ahora
  // vive server-side, una cookie httpOnly por slot, renovable sin límite de
  // tiempo), no cambia nada sobre el access token, que sigue siendo de vida
  // corta y solo en memoria a propósito (protección XSS). No hace falta que
  // el backend "resuelva" el access token por sí solo -- seguiría habiendo
  // que pedir uno nuevo en cada resume si no lo cacheáramos acá, con una
  // llamada de red evitable.
  private pausedSessions: PausedTokens[] = []
  // Ver pauseCurrentSession/resumePreviousSession/getSessionEpoch.
  private sessionEpoch = 0
  private refreshTimeout: ReturnType<typeof setTimeout> | null = null
  private isRestoringSession: boolean = false
  private sessionRestored: boolean = false
  private restorePromise: Promise<void> | null = null
  private userFetched: boolean = false  // Flag para evitar múltiples llamadas a /auth/me
  private userFetchPromise: Promise<User> | null = null  // Singleton promise para getCurrentUser
  // Promesa compartida del refresh en curso -- cualquier llamador concurrente
  // espera esta MISMA promesa en vez de disparar su propio POST /auth/refresh
  // (el refresh token rota, uso unico: dos POST simultaneos hacen que uno
  // pierda con 401 aunque el otro haya tenido exito un instante antes)
  private refreshPromise: Promise<RefreshResponse> | null = null

  /**
   * Obtener configuración pública de Turnstile (sin auth)
   */
  async getTurnstileConfig(): Promise<TurnstileConfig> {
    const response = await axiosInstance.get('/auth/turnstile-config')
    return response.data
  }

  /**
   * Iniciar sesión
   * Retorna: access_token en response, refresh_token en httpOnly cookie
   */
  async login(credentials: LoginCredentials): Promise<LoginResult> {
    const response = await axiosInstance.post('/auth/login', credentials)
    const loginData = response.data.data

    // Si el usuario tiene 2FA, el backend retorna requires_2fa sin access_token
    if (loginData.requires_2fa) {
      return loginData as TwoFactorLoginResponse
    }

    // Login normal: guardar access token en memoria
    this.accessToken = loginData.access_token
    return loginData as LoginResponse
  }

  async verifyTwoFactorLogin(preAuthToken: string, code: string): Promise<LoginResponse> {
    const response = await axiosInstance.post('/auth/2fa/verify-login', {
      pre_auth_token: preAuthToken,
      code,
    })
    const loginData = response.data.data
    this.accessToken = loginData.access_token
    return loginData as LoginResponse
  }

  async get2FAStatus(): Promise<TwoFactorStatus> {
    const response = await axiosInstance.get('/auth/2fa/status')
    return response.data.data
  }

  async setup2FA(): Promise<TwoFactorSetupData> {
    const response = await axiosInstance.post('/auth/2fa/setup')
    return response.data.data
  }

  async enable2FA(code: string): Promise<void> {
    await axiosInstance.post('/auth/2fa/enable', { code })
  }

  async disable2FA(code: string): Promise<void> {
    await axiosInstance.post('/auth/2fa/disable', { code })
  }

  /**
   * Cambiar la contraseña del usuario actual (ya logueado). Migrado desde
   * modules/preferencias/services/security.service.ts.
   */
  async changePassword(data: PasswordChange): Promise<void> {
    const response = await axiosInstance.post('/users/me/change-password', {
      current_password: data.current_password,
      new_password: data.new_password,
    })
    return response.data
  }

  /**
   * Obtener las políticas de seguridad del sistema (longitud mínima de
   * contraseña, requisitos, etc.). Migrado desde
   * modules/preferencias/services/security.service.ts.
   */
  async getSecurityPolicies(): Promise<SecurityPolicies> {
    const response = await axiosInstance.get('/user/preferences/security-policies')
    return response.data.data || response.data
  }

  /**
   * Registrar usuario
   * El usuario debe hacer login después del registro
   */
  async register(data: RegisterData): Promise<User> {
    const response = await axiosInstance.post('/auth/register', data)
    // Backend devuelve el usuario directamente (no envuelto en SuccessResponse)
    return response.data
  }

  /**
   * Cerrar sesión
   * Limpia el access token de memoria y notifica al backend para limpiar la cookie
   */
  async logout(): Promise<void> {
    // Limpiar auto-refresh
    this.clearAutoRefresh()

    try {
      // Notificar al backend para limpiar la cookie
      await axiosInstance.post('/auth/logout')
    } finally {
      // Limpiar token de memoria siempre
      this.accessToken = null
      // Un logout real (boton "Cerrar sesion") siempre cierra TODO, incluidas
      // las sesiones que hubiera pausadas por "Cambiar de usuario" -- no hay
      // "volver" despues de esto, a diferencia de resumePreviousSession().
      this.discardPausedSessions()
      // Resetear flags de sesión
      this.sessionRestored = false
      this.isRestoringSession = false
      this.restorePromise = null
      // Resetear flags de usuario fetch
      this.userFetched = false
      this.userFetchPromise = null

      // Limpiar localStorage (preferencias, filtros, etc.)
      // Esto asegura que el siguiente usuario no vea las preferencias del anterior
      cleanupAllExceptSettings()
    }
  }

  /**
   * Notifica al backend que cierre la sesión ACTIVA en este momento, sin
   * tocar tokens en memoria, sin limpiar localStorage ni la pila de
   * pausadas -- a diferencia de logout(). Uso específico: justo antes de
   * "Volver" a una sesión pausada (useAuth.returnToPreviousUser).
   *
   * Por qué hace falta: en web, el refresh token vive en una cookie
   * httpOnly que JS no puede leer ni restaurar -- resumePreviousSession()
   * solo puede devolver el accessToken en memoria del usuario pausado, la
   * cookie del navegador sigue siendo la del usuario temporal que se
   * abandona. Sin este logout, esa sesión temporal queda "escondida" pero
   * viva del lado del backend: si el accessToken restaurado expira más
   * tarde, el próximo refresh reactivo usa esa cookie y vuelve a autenticar
   * en silencio como el usuario temporal, aunque la UI siga mostrando al
   * restaurado (confirmado en vivo contra Docker local, no es hipotético).
   * Con este logout, ese refresh futuro simplemente falla limpio y pide
   * volver a loguear -- degradación segura en vez de suplantación
   * silenciosa. Best-effort a propósito (no lanza): si falla, igual seguimos
   * con la restauración local.
   */
  async closeActiveSessionOnBackend(): Promise<void> {
    try {
      // scope=current: cierra SOLO la sesión del slot activo (la temporal
      // que se abandona), no toda la pila -- el default del backend
      // (scope=all, el que usa logout() más abajo) cierra todo, que es lo
      // que NO queremos acá: la sesión a la que se está volviendo debe
      // quedar intacta. El slot lo agrega el interceptor de axiosInstance
      // (X-Session-Slot, ver axios.ts) a partir de pausedSessions.length,
      // que en este punto todavía es el de la sesión que se abandona --
      // este método corre ANTES de resumePreviousSession() (ver
      // useAuth.returnToPreviousUser).
      await axiosInstance.post('/auth/logout', null, { params: { scope: 'current' } })
    } catch {
      // best-effort
    }
  }

  /**
   * Cambiar de usuario (temporal) — PARTE 1: pausar
   *
   * Guarda el access token de la sesion activa en una pila y deja al
   * servicio listo para loguear a otro usuario encima, SIN llamar a
   * cleanupAllExceptSettings() ni tocar localStorage de la app (filtros,
   * etc.) -- a diferencia de logout(), esto es reversible.
   *
   * Async a propósito: si hay un refreshToken() en vuelo (disparado por un
   * 401 justo antes de pausar), se espera a que termine ANTES de pausar. Sin
   * esto, esa respuesta tardía pisaría accessToken/cookie del usuario que se
   * loguee encima cuando resuelva -- en web, incluso rotaría la cookie
   * httpOnly compartida hacia el usuario viejo sin que la UI lo note
   * (encontrado en auditoría, ver PROGRESO_auditor-switch-user.md).
   */
  async pauseCurrentSession(): Promise<void> {
    if (this.refreshPromise) {
      await this.refreshPromise.catch(() => {})
    }
    this.pausedSessions.push({
      accessToken: this.accessToken,
    })
    this.accessToken = null
    // Se van a volver a pedir /auth/me y permisos para el usuario nuevo
    this.userFetched = false
    this.userFetchPromise = null
    this.sessionEpoch++
  }

  /**
   * Cambiar de usuario (temporal) — PARTE 2: volver
   *
   * Restaura la sesion pausada mas reciente (LIFO). Devuelve false si no
   * habia ninguna pausada -- el llamador (useAuth.returnToPreviousUser) no
   * deberia poder invocar esto sin verificar hasPausedSession() antes, pero
   * queda a prueba de llamadas fuera de orden.
   */
  resumePreviousSession(): boolean {
    const previous = this.pausedSessions.pop()
    if (!previous) return false
    this.accessToken = previous.accessToken
    this.userFetched = false
    this.userFetchPromise = null
    this.sessionEpoch++
    return true
  }

  /** true si hay al menos una sesion pausada por "Cambiar de usuario". */
  hasPausedSession(): boolean {
    return this.pausedSessions.length > 0
  }

  /**
   * Descarta todas las sesiones pausadas sin tocar el token activo ni el
   * backend -- para cuando otro camino ya hizo su propia limpieza (ej. el
   * interceptor de axios ante un refresh rechazado, axios.ts) y solo falta
   * sincronizar esta pila para que no queden tokens huérfanos en memoria.
   */
  discardPausedSessions(): void {
    this.pausedSessions = []
  }

  /**
   * Contador que se incrementa cada vez que cambia de identidad la sesion
   * activa (pause/resume). useAuth.switchUser lo usa para detectar si otra
   * operacion (ej. un "Volver" concurrente) tocó la sesión mientras un login
   * estaba en vuelo, y así no pisar con datos viejos lo que quedó activo.
   */
  getSessionEpoch(): number {
    return this.sessionEpoch
  }

  /**
   * Slot de sesión activo en este momento (0 = sesión base, sin nada
   * pausado; N = hay N sesiones pausadas debajo de la que está activa
   * ahora). Coincide siempre con la profundidad de `pausedSessions`: cada
   * `pauseCurrentSession()` empuja una entrada y el próximo login/refresh ya
   * corre con el slot incrementado; cada `resumePreviousSession()` la saca y
   * el slot vuelve a bajar. Es lo que viaja en el header `X-Session-Slot`
   * (ver axios.ts) para que el backend sepa qué cookie `refresh_token` /
   * `refresh_token_slot_{n}` mirar -- el número en sí no autoriza nada, solo
   * enruta, la identidad la sigue probando el JWT dentro de esa cookie.
   */
  getActiveSlot(): number {
    return this.pausedSessions.length
  }

  /**
   * Obtener usuario actual - SINGLETON CON BLINDAJE TOTAL
   * 
   * ⚠️ IMPORTANTE: USAR SOLO EN authLoader()
   * 
   * Mecanismo de blindaje de 3 capas:
   * 1. userFetched flag - si ya completó, rechaza automaticamente nuevos intentos
   * 2. userFetchPromise - si hay una en progreso, retorna la misma promise
   * 3. clearAutoRefresh() - si falla, limpia timers
   * 
   * Esto previene:
   * - Múltiples llamadas a /auth/me desde componentes
   * - Race conditions con múltiples tabs
   * - Loops infinitos de refresh
   * 
   * ❌ NUNCA llamar desde:
   * - useEffect en componentes
   * - Watchers
   * - Event handlers
   */
  async getCurrentUser(): Promise<User> {
    // CAPA 1: Si ya fetched la data, retornar inmediatamente el cache
    if (this.userFetched && this.userFetchPromise) {
      return this.userFetchPromise
    }

    // CAPA 2: Si hay una petición en progreso, esperar a ella
    if (this.userFetchPromise) {
      return this.userFetchPromise
    }

    // CAPA 3: Crear la promise singleton
    this.userFetchPromise = (async () => {
      try {
        const response = await axiosInstance.get('/auth/me')
        // Backend devuelve: { status, message, data: User }
        const user = response.data.data
        this.userFetched = true
        return user
      } catch (error) {
        // Si falla (401, 403, etc.), limpiar todo -- incluidas sesiones
        // pausadas por "Cambiar de usuario": si la sesión activa quedó rota,
        // no hay a qué volver de forma confiable (encontrado en auditoría de
        // cierre: pauseCurrentSession/resumePreviousSession resetean
        // userFetched, así que un authLoader() posterior puede volver a
        // llamar acá y, si falla, dejaba pausedSessions huérfana).
        this.accessToken = null
        this.clearAutoRefresh()
        this.discardPausedSessions()
        this.userFetched = false
        this.userFetchPromise = null
        throw error
      }
    })()

    return this.userFetchPromise
  }

  /**
   * Refrescar token
   * El refresh_token se envía automáticamente en cookie httpOnly
   * Retorna nuevo access_token y nuevo refresh_token (token rotation)
   * 
   * NOTA: Ya no usa timer automático (setupAutoRefresh)
   * Solo refresh reactivo: cuando axios detecta 401 en una petición
   */
  /**
   * Refresca el access token. Dedupeado con `refreshPromise`: si ya hay un
   * refresh en curso, cualquier llamador concurrente espera esa MISMA
   * promesa en vez de disparar su propio POST (evita la carrera contra la
   * rotación de un solo uso del refresh token -- ver comentario en el campo).
   */
  async refreshToken(): Promise<RefreshResponse> {
    if (this.refreshPromise) return this.refreshPromise

    const epochAtStart = this.sessionEpoch
    this.refreshPromise = this.doRefreshToken(epochAtStart).finally(() => {
      this.refreshPromise = null
    })
    return this.refreshPromise
  }

  /**
   * @param epochAtStart snapshot de sessionEpoch tomado ANTES de disparar el
   * POST /auth/refresh. Si al resolver (o fallar) el epoch ya cambió --
   * porque pauseCurrentSession/resumePreviousSession corrió mientras tanto,
   * ver "Cambiar de usuario" -- esta respuesta pertenece a una identidad que
   * ya no es la activa: se ignoran sus efectos (no pisar accessToken/cookie
   * de quien sea que esté activo ahora). Defensa adicional a que
   * pauseCurrentSession ya espera cualquier refresh en vuelo antes de pausar.
   */
  private async doRefreshToken(epochAtStart: number): Promise<RefreshResponse> {
    try {
      // Axios plano (sin el interceptor de axiosInstance): si este POST
      // devuelve 401, no debe reentrar la logica de refresh del interceptor.
      //
      // POR ESO MISMO no recibe el header X-Session-Slot del interceptor de
      // axios.ts -- hay que agregarlo acá a mano. Sin esto, el refresh
      // reactivo (el mecanismo central de "Cambiar de usuario" en web) manda
      // siempre slot 0 por default, ignora la cookie refresh_token_slot_{n}
      // de cualquier sesión pausada o activa que no sea la base, y resucita
      // el bug original: reautenticación silenciosa con la identidad
      // equivocada (hallazgo de la auditoría, ver AUDITORIA_disenos.md punto
      // 1 -- condición no negociable del visto bueno).
      //
      // Se lee this.pausedSessions.length en el momento de armar el request
      // (no un valor cacheado en epochAtStart): pauseCurrentSession() ya
      // espera cualquier refreshPromise en vuelo antes de empujar a la pila,
      // así que para cuando este POST sale, la profundidad todavía no cambió
      // por una pausa concurrente -- es seguro leerla acá tal cual.
      const response = await axios.post(
        `${getApiUrl()}/auth/refresh`,
        {},
        {
          withCredentials: true,
          headers: {
            ...(getTenantSlug() ? { 'X-Tenant-Slug': getTenantSlug() } : {}),
            'X-Session-Slot': String(this.pausedSessions.length),
          },
        }
      )

      // Backend devuelve: { status, message, data: { access_token, token_type } }
      const refreshData = response.data.data

      if (epochAtStart === this.sessionEpoch) {
        // Guardar nuevo access token en memoria — el refresh token nuevo
        // queda guardado automáticamente en la cookie httpOnly
        this.accessToken = refreshData.access_token
      }

      // NO reiniciar auto-refresh - usar refresh reactivo (401)

      return refreshData
    } catch (error) {
      // Si falla el refresh (cookie/refresh token expirado, inválido, etc.)
      // Limpiar todo -- solo si nadie cambio de identidad mientras tanto
      // (ver comentario del parametro epochAtStart arriba).
      if (epochAtStart === this.sessionEpoch) {
        this.accessToken = null
        this.clearAutoRefresh()
      }
      throw error
    }
  }

  /**
   * Configurar auto-refresh (DEPRECADO)
   * Ya no se usa - refresh reactivo (401) es más simple y seguro
   * Se mantiene por compatibilidad pero no se llama desde ningún lado
   */
  setupAutoRefresh(ms: number = AUTO_REFRESH_INTERVAL): void {
    // Limpiar timeout anterior si existe
    this.clearAutoRefresh()
    
    this.refreshTimeout = setTimeout(async () => {
      try {
        await this.refreshToken()
      } catch (error) {
        console.error('Error en auto-refresh:', error)
        // Si falla el auto-refresh, limpiar token
        this.accessToken = null
      }
    }, ms)
  }

  /**
   * Limpiar auto-refresh
   */
  clearAutoRefresh(): void {
    if (this.refreshTimeout) {
      clearTimeout(this.refreshTimeout)
      this.refreshTimeout = null
    }
  }

  /**
   * Solicitar reseteo de contraseña
   */
  async requestPasswordReset(email: string): Promise<void> {
    await axiosInstance.post('/auth/forgot-password', { email })
  }

  /**
   * Resetear contraseña
   */
  async resetPassword(token: string, password: string): Promise<void> {
    await axiosInstance.post('/auth/reset-password', { token, password })
  }

  /**
   * Verificar si el usuario está autenticado (DEPRECADO)
   * 
   * ❌ NO USAR - duplica estado
   * 
   * ✅ USAR LUGAR:
   * const state = useAuthStore.getState()
   * const isAuth = state.isAuthenticated  // Derivado de: user !== null && initialized
   */
  isAuthenticated(): boolean {
    console.warn('⚠️ isAuthenticated() deprecado. Usa useAuthStore.getState().isAuthenticated')
    return !!this.accessToken
  }

  /**
   * Verificar si la sesión ya fue restaurada
   */
  isSessionRestored(): boolean {
    return this.sessionRestored
  }

  /**
   * Verificar si se está restaurando la sesión
   */
  isRestoring(): boolean {
    return this.isRestoringSession
  }

  /**
   * Esperar a que termine la restauración de sesión
   * Si no se ha iniciado, la inicia
   */
  async waitForSessionRestore(): Promise<void> {
    // Si ya se restauró, retornar inmediatamente
    if (this.sessionRestored) return
    
    // Si hay una restauración en progreso, esperar
    if (this.restorePromise) {
      await this.restorePromise
      return
    }
    
    // Si no se ha iniciado, iniciar la restauración
    await this.restoreSession()
  }

  /**
   * Iniciar restauración de sesión
   * Con timeout máximo de 3 segundos para no bloquear la UI
   */
  async restoreSession(): Promise<boolean> {
    // Si ya se restauró, no hacerlo de nuevo
    if (this.sessionRestored) {
      return !!this.accessToken  // Retornar directamente sin llamar isAuthenticated()
    }

    // Si ya se está restaurando, esperar (con timeout)
    if (this.isRestoringSession && this.restorePromise) {
      try {
        await Promise.race([
          this.restorePromise,
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Session restore timeout')), 3000)
          ),
        ])
      } catch {
        console.log('⏱️ Timeout en restauración de sesión (3s)')
      }
      return !!this.accessToken
    }

    // Marcar como restaurando
    this.isRestoringSession = true
    
    this.restorePromise = (async () => {
      try {
        // Si ya hay token en memoria, validar
        if (this.accessToken) {
          console.log('🔑 Token en memoria encontrado')
          this.sessionRestored = true
          // NO llamar setupAutoRefresh() - usar refresh reactivo
          return
        }

        // Intentar obtener nuevo token con refresh token de la cookie
        // Timeout de 6 segundos - balance entre dar tiempo suficiente y no bloquear UI
        console.log('🔄 Intentando restaurar sesión con refresh token...')
        await Promise.race([
          this.refreshToken(),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Refresh token timeout')), 6000)
          ),
        ])
        console.log('✅ Sesión restaurada exitosamente')
        this.sessionRestored = true
      } catch (error) {
        console.log('❌ No se pudo restaurar sesión:', error)
        // Solo marcar como restaurado si es un error real, no timeout de red
        const isNetworkError = error instanceof Error && 
          (error.message.includes('Network Error') || error.message.includes('CORS'))
        
        if (!isNetworkError) {
          this.sessionRestored = true // Solo marcar si no es error de red
        }
        this.accessToken = null
      } finally {
        this.isRestoringSession = false
      }
    })()

    // Esperar con timeout máximo de 3.5 segundos
    try {
      await Promise.race([
        this.restorePromise,
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('Session restore timeout')), 3500)
        ),
      ])
    } catch {
      console.log('⏱️ Timeout en restauración de sesión')
    }
    
    return !!this.accessToken  // Retornar directamente sin llamar isAuthenticated()
  }

  /**
   * Obtener token actual (para uso interno del axios interceptor)
   */
  getAccessToken(): string | null {
    return this.accessToken
  }

  /**
   * Establecer token (para uso del axios interceptor en refresh)
   */
  setAccessToken(token: string | null): void {
    this.accessToken = token
  }
}

export const authService = new AuthService()
