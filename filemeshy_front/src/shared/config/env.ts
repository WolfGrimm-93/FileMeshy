/**
 * Configuración de variables de entorno
 * Centraliza el acceso a variables de entorno con validación.
 *
 * En dev: usa VITE_API_URL del .env. En prod: se calcula contra el dominio
 * actual (ver initConfig), para que la misma imagen sirva cualquier dominio
 * sin tocar CORS ni relajar el SameSite de la cookie de sesión.
 */

const getEnvVar = (key: string, defaultValue?: string): string => {
  const value = import.meta.env[key] || defaultValue
  if (value === undefined || value === null) {
    console.warn(`⚠️ Variable de entorno ${key} no está definida`)
  }
  return value ?? ''
}

// URL activa — se actualiza en initConfig() antes de renderizar la app
let _apiUrl: string = getEnvVar('VITE_API_URL', 'http://localhost:8001/api/v1')

// ── Multi-tenancy (fase 2 -- backend en DEPLOYMENT_MODE=cloud) ──────────────
// Slug del tenant activo. Dinamico (no baked-in): se puede elegir desde el
// campo "Empresa" del login (ver LoginForm/useLoginForm) y persiste en
// localStorage para que sobreviva un refresh de pagina -- axios.ts lo lee en
// cada request via getTenantSlug(), incluido el refresh de sesion al arrancar
// la app. Vacio en toda instalacion normal (single-tenant): axios.ts no manda
// X-Tenant-Slug si esto esta vacio, cero cambio de comportamiento fuera del
// lab de tenants.
const TENANT_SLUG_STORAGE_KEY = 'filemeshy_tenant_slug'
let _tenantSlug: string = (typeof localStorage !== 'undefined' && localStorage.getItem(TENANT_SLUG_STORAGE_KEY)) || getEnvVar('VITE_TENANT_SLUG', '')

export const getTenantSlug = () => _tenantSlug

export const setTenantSlug = (slug: string) => {
  _tenantSlug = slug.trim()
  if (typeof localStorage !== 'undefined') {
    if (_tenantSlug) {
      localStorage.setItem(TENANT_SLUG_STORAGE_KEY, _tenantSlug)
    } else {
      localStorage.removeItem(TENANT_SLUG_STORAGE_KEY)
    }
  }
}

// Modo activo: 'browser' | 'dev'
let _activeMode: 'browser' | 'dev' = 'dev'

/** Retorna la URL base del API activa */
export const getApiUrl = () => _apiUrl

/** Retorna qué modo de conexión está activo */
export const getActiveMode = (): 'browser' | 'dev' => _activeMode

/**
 * Inicializa la configuración dinámica. Debe llamarse ANTES de renderizar la
 * app (ver main.tsx).
 *
 * En dev: usa VITE_API_URL del .env.development.
 * En prod: calcula la URL contra el dominio actual (window.location.origin),
 * para que la misma imagen sirva cualquier dominio que Traefik/nginx le
 * apunte (multi-dominio) con /api same-origin siempre -- sin tocar CORS ni
 * relajar el SameSite de la cookie de sesion.
 */
export async function initConfig(): Promise<void> {
  if (import.meta.env.PROD && typeof window !== 'undefined') {
    _apiUrl = `${window.location.origin}/api/v1`
    _activeMode = 'browser'
  } else {
    _activeMode = 'dev'
  }
}

export const env = {
  // API Backend Principal — usar getApiUrl() para el valor dinámico
  get apiUrl() { return _apiUrl },
  apiTimeout: parseInt(getEnvVar('VITE_API_TIMEOUT', '30000')),

  // Autenticación
  tokenKey: getEnvVar('VITE_TOKEN_KEY', 'filemeshy_token'),
  refreshTokenKey: getEnvVar('VITE_REFRESH_TOKEN_KEY', 'filemeshy_refresh_token'),

  // Multi-tenancy (fase 2): mostrar el campo "Empresa" en el login. Solo true
  // en builds del lab de tenants (VITE_ENABLE_TENANT_SELECTOR) -- en toda
  // instalacion normal (single-tenant) queda false, el campo ni se renderiza.
  tenantSelectorEnabled: getEnvVar('VITE_ENABLE_TENANT_SELECTOR', 'false') === 'true',

  // App
  appName: getEnvVar('VITE_APP_NAME', 'FileMeshy'),
  appVersion: getEnvVar('VITE_APP_VERSION', '1.0.0'),

  // Modo
  isDev: import.meta.env.DEV,
  isProd: import.meta.env.PROD,
  mode: import.meta.env.MODE,
}

export type Env = typeof env
