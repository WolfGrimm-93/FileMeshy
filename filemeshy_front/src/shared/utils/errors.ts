/**
 * Extracción del mensaje de error real de una respuesta de la API.
 *
 * `error.message` de un `AxiosError` es siempre el genérico de axios
 * ("Request failed with status code 400"), NUNCA el `detail` real que
 * devuelve el backend -- por eso `error instanceof Error ? error.message :
 * fallback` muestra al usuario un mensaje inútil en vez del motivo real
 * (permiso faltante, validación de negocio, límite excedido, etc.).
 *
 * Misma lógica que usaba `apiClient` internamente (src/shared/config/api.ts),
 * extraída acá para poder reusarla desde módulos que llaman a `axiosInstance`
 * directo (sin pasar por `apiClient`) y reciben el `AxiosError` crudo.
 */
import type { AxiosError } from 'axios'

export function extractErrorMessage(error: unknown, fallback = 'Ocurrió un error inesperado'): string {
  if (error && typeof error === 'object' && 'response' in error) {
    const axiosError = error as AxiosError
    const data = axiosError.response?.data as any | undefined

    // Errores con estructura { code, message } (ej. password reset)
    if (data?.code && data?.message) {
      return `${data.code}: ${data.message}`
    }

    // Misma estructura pero anidada en data.data (fallback)
    if (data?.data?.code && data?.data?.message) {
      return `${data.data.code}: ${data.data.message}`
    }

    // Errores de validación de Pydantic (422): detail es un array
    if (Array.isArray(data?.detail)) {
      const validationError = data.detail[0]
      if (validationError && 'msg' in validationError) {
        return validationError.msg
      }
    }

    // Caso más común: detail como string (ej. reglas de negocio del backend)
    if (typeof data?.detail === 'string') {
      return data.detail
    }

    // Errores con detail como objeto custom
    if (data?.detail && typeof data.detail === 'object') {
      const errorObj = data.detail as Record<string, unknown>
      if (errorObj.message) return String(errorObj.message)
      if (errorObj.detail) return String(errorObj.detail)
    }

    return axiosError.message || fallback
  }

  if (error instanceof Error) {
    return error.message
  }

  return fallback
}
