/**
 * Cliente HTTP standalone del panel de plataforma (administración de
 * tenants, modo cloud).
 *
 * DELIBERADAMENTE separado de `@/shared/config/axios.ts`: ese cliente
 * maneja JWT/refresh-token/CSRF/X-Tenant-Slug, todo irrelevante -- y hasta
 * contraproducente -- acá, porque este panel NO es un usuario de ningún
 * tenant. Se autentica con un secreto compartido (`X-Platform-Key`) contra
 * `app/platform/router.py` (`get_platform_admin`), completamente por fuera
 * del sistema de login/RBAC normal de la app (ver contrato de la Ronda 8).
 *
 * Tampoco usa `@/shared/config/api.ts` (el `apiClient` compartido): ese
 * asume el envelope `{status, data}` que envuelve el resto de la API
 * (`response.data.data`). El contrato de `/platform/*` dice que la
 * respuesta es el modelo Pydantic directo, sin envelope -- por eso acá se
 * expone la instancia de axios cruda y cada método de `tenants.service.ts`
 * lee `response.data` tal cual.
 *
 * OJO -- verificado en vivo (curl + Playwright, Ronda 8): al momento de
 * escribir esto, el backend real (`app/platform/router.py`) TODAVÍA envuelve
 * las 4 respuestas 200 en `SuccessResponse` (`{status, message, data,
 * cached}`), pese a que el contrato pide la respuesta directa -- confirmado
 * también leyendo el archivo en disco, no es un contenedor desactualizado.
 * Se puede volver inofensivo de este lado: el interceptor de abajo
 * desenvuelve automáticamente el envelope si lo detecta, y deja pasar sin
 * tocar cualquier respuesta que ya venga en el formato directo del contrato
 * -- así el panel funciona contra el backend real de HOY sin dejar de ser
 * compatible si el backend corrige esto más adelante.
 *
 * (`TenantCreateResponse.admin_email` -- que en un momento faltaba acá --
 * ya lo agregó el otro agente en `app/platform/schemas.py`, cubierto por
 * test; no queda ningún gap de campos pendiente, solo el del envelope de
 * arriba.)
 */
import axios, { type AxiosInstance } from 'axios'
import { env, getApiUrl } from '@/shared/config/env'

// Misma clave que usa `platformAuthStore.ts` para persistir en sessionStorage
// (NO localStorage a propósito -- es un secreto de alto privilegio, la
// sesión del panel debe morir al cerrar la pestaña).
export const PLATFORM_KEY_STORAGE_KEY = 'filemeshy_platform_key'

const platformAdminApi: AxiosInstance = axios.create({
  timeout: env.apiTimeout,
  // Sin cookies: esta API no usa sesión de cookie httpOnly, solo el header
  // de la key de plataforma.
  withCredentials: false,
  headers: {
    'Content-Type': 'application/json; charset=utf-8',
    'Accept': 'application/json; charset=utf-8',
  },
})

// Interceptor de request -- inyecta baseURL dinámica (igual que
// shared/config/axios.ts, para que initConfig() pueda cambiar la URL antes
// de la primera petición) + el header X-Platform-Key leído directo de
// sessionStorage (no del store de React, para no acoplar este cliente HTTP
// a React).
platformAdminApi.interceptors.request.use((config) => {
  if (!config.baseURL) {
    config.baseURL = `${getApiUrl()}/platform`
  }

  try {
    const key = sessionStorage.getItem(PLATFORM_KEY_STORAGE_KEY)
    if (key && config.headers) {
      config.headers['X-Platform-Key'] = key
    }
  } catch {
    // sessionStorage no disponible (ej. modo privado con storage bloqueado)
    // -- la request sale sin key y el backend la rechaza con 401, que ya
    // maneja el interceptor de response de abajo.
  }

  return config
})

// Shape del envelope legado ({status, message, data, ...}) que usa el resto
// de la app (ver shared/config/axios.ts::ApiResponse) -- el contrato de
// /platform/* dice que NO debería aparecer acá, pero el backend real (ver
// comentario de arriba) todavía lo manda. `status`+`message`+`data` los tres
// presentes a la vez es lo bastante específico como para no confundirse con
// ninguno de los modelos reales (`TenantListItem`/`TenantCreateResult`/etc.
// no tienen esos 3 campos).
function isLegacyEnvelope(value: unknown): value is { status: unknown; message: unknown; data: unknown } {
  return (
    !!value &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    'status' in value &&
    'message' in value &&
    'data' in value
  )
}

// Interceptor de response -- 2 responsabilidades:
// 1) Desenvolver el envelope legado si el backend lo manda (ver comentario
//    de arriba del archivo) para que tenants.service.ts pueda leer
//    `response.data` tal cual el contrato promete, sin importar cuál de los
//    2 formatos responda el backend en cada momento.
// 2) En 401/403 la key guardada ya no sirve (era incorrecta o la
//    revocaron): se limpia de sessionStorage para que el guard mande al
//    login en el próximo render, en vez de quedar reintentando con una key
//    inválida.
platformAdminApi.interceptors.response.use(
  (response) => {
    if (isLegacyEnvelope(response.data)) {
      response.data = response.data.data
    }
    return response
  },
  (error) => {
    const statusCode = error?.response?.status
    if (statusCode === 401 || statusCode === 403) {
      try {
        sessionStorage.removeItem(PLATFORM_KEY_STORAGE_KEY)
      } catch {
        // Ignorar -- mismo caso de sessionStorage no disponible de arriba.
      }
    }
    return Promise.reject(error)
  }
)

export default platformAdminApi

/**
 * Errores de `/platform/*` vienen en el formato crudo de `HTTPException` de
 * FastAPI (`{detail: string}`) -- NO el `{status, message, data}` del resto
 * de la app (`extractErrorMessage` de `@/shared/utils/errors` asume ese
 * otro formato, por eso no se reusa acá).
 */
export function getPlatformErrorStatus(error: unknown): number | undefined {
  if (axios.isAxiosError(error)) {
    return error.response?.status
  }
  return undefined
}

export function getPlatformErrorMessage(error: unknown, fallback = 'Error desconocido'): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
    if (error.message) {
      return error.message
    }
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}
