/**
 * Servicio de subida resumable por partes (multipart directo a MinIO).
 *
 * Contrato REAL verificado leyendo `filemeshy_back/app/uploads/schemas.py` +
 * `service.py` (implementado en paralelo por otros 2 agentes en esta misma
 * ronda -- código ya presente al momento de escribir esto, aunque el stack
 * corriendo todavía puede no estar levantado/migrado):
 *
 *   POST /uploads/initiate                       -> InitiateUploadResponse
 *   POST /uploads/{session_id}/refresh-part-urls  -> RefreshPartUrlsResponse
 *   POST /uploads/{session_id}/complete           -> FileOut (con scan_status,
 *        ver OJO en types.ts -- a esta fecha `app/files/schemas.py` todavía
 *        no expone ese campo, Pydantic lo va a dropear del JSON hasta que lo
 *        agreguen)
 *   POST /uploads/{session_id}/abort              -> UploadSessionOut (200,
 *        no 204 -- no nos importa el body, se ignora)
 *
 * Estos 4 endpoints son del backend de la app -- usan `axiosInstance`
 * (mismo JWT/CSRF/refresh automático que cualquier otro endpoint, ver
 * `files.service.ts`). La subida de bytes en sí (el PUT a cada `url` de
 * `part_urls`) NO pasa por acá: esa es una request cruda contra un proxy de
 * nginx→MinIO, sin JWT, implementada en `lib/multipartUploader.ts`.
 */
import axiosInstance from '@/shared/config/axios'
import type { FileOut } from '../types'

export interface InitiateUploadParams {
  file_name: string
  size_bytes: number
  mime_type: string
  folder_id?: string
}

export interface PartUrl {
  part_number: number
  url: string
}

export interface InitiateUploadResponse {
  upload_session_id: string
  part_urls: PartUrl[]
  part_size_bytes: number
  expires_at: string
}

export interface ConfirmedPart {
  part_number: number
  etag: string
}

/** Parte que MinIO confirma como ya subida (`ListParts` real, no lo que diga
 *  IndexedDB) -- trae `size_bytes` además de `part_number`/`etag`, aunque acá
 *  no lo usamos (ya conocemos el tamaño de cada parte por `buildPartRanges`). */
export interface CompletedPart extends ConfirmedPart {
  size_bytes: number
}

export interface RefreshPartUrlsResponse {
  part_urls: PartUrl[]
  /** OJO nombre real del campo: `completed_parts`, NO `already_uploaded` --
   *  el contrato original que se nos dio para arrancar a construir decía
   *  `already_uploaded`; se corrigió acá tras leer `app/uploads/schemas.py`
   *  del backend real. */
  completed_parts: CompletedPart[]
  expires_at: string
}

/**
 * Error tipado para el 503 de admission control ("demasiadas subidas
 * grandes en simultáneo") -- lleva el `Retry-After` (en segundos, si el
 * backend lo manda) para que quien orqueste la subida pueda reintentar
 * respetándolo en vez de fallar directo.
 */
export class UploadAdmissionError extends Error {
  retryAfterSeconds: number | undefined

  constructor(retryAfterSeconds: number | undefined) {
    super('El servidor está ocupado con otras subidas grandes')
    this.name = 'UploadAdmissionError'
    this.retryAfterSeconds = retryAfterSeconds
  }
}

function parseRetryAfter(value: string | undefined | null): number | undefined {
  if (!value) return undefined
  const seconds = Number(value)
  if (Number.isFinite(seconds) && seconds >= 0) return seconds
  // Retry-After también puede venir como fecha HTTP -- caso raro para este
  // endpoint puntual, pero lo cubrimos igual en vez de ignorarlo.
  const asDate = Date.parse(value)
  if (!Number.isNaN(asDate)) {
    return Math.max(0, Math.round((asDate - Date.now()) / 1000))
  }
  return undefined
}

class UploadsService {
  private basePath = '/uploads'

  async initiate(params: InitiateUploadParams): Promise<InitiateUploadResponse> {
    try {
      const response = await axiosInstance.post<InitiateUploadResponse>(`${this.basePath}/initiate`, params)
      return response.data
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'response' in error) {
        const axiosError = error as { response?: { status?: number; headers?: Record<string, string> } }
        // El backend real (`app/uploads/service.py::initiate_upload`) devuelve 503 por
        // VARIOS motivos -- solo uno es admission control real (demasiadas subidas
        // grandes en curso); en teoría ese caso trae `Retry-After: 30`, los demás
        // (MinIO caído, servicio de firma caído) no deberían traerlo.
        //
        // OJO -- verificado en vivo con Playwright contra el backend real (Ronda 9):
        // el `Retry-After` que pone `HTTPException(..., headers={"Retry-After": "30"})`
        // en el admission-control real NUNCA llega al browser (headers de la respuesta
        // 503 capturados en la verificación: sin `retry-after` en ningún lado -- se
        // pierde en algún punto del lado del backend, no es un tema de CORS ya que
        // `/api/` es same-origin). Con el gate original (exigir el header) esto hacía
        // que la admission-control REAL cayera al error genérico de una sola vez, sin
        // reintento automático -- exactamente lo que este código existe para evitar.
        // Mientras el backend no lo corrija: se trata CUALQUIER 503 de este endpoint
        // como candidato a admission control (con `retryAfterSeconds: undefined` si no
        // viene el header, así el store aplica su propio backoff por defecto) -- el
        // límite de reintentos automáticos acotados (no infinitos) vive en
        // `uploadsStore.ts::initiateWithAdmissionRetry`, que es quien evita el
        // "spinner infinito" ante una falla de infra genuina, no este gate.
        if (axiosError.response?.status === 503) {
          throw new UploadAdmissionError(parseRetryAfter(axiosError.response.headers?.['retry-after']))
        }
      }
      throw error
    }
  }

  async refreshPartUrls(sessionId: string): Promise<RefreshPartUrlsResponse> {
    const response = await axiosInstance.post<RefreshPartUrlsResponse>(
      `${this.basePath}/${sessionId}/refresh-part-urls`
    )
    return response.data
  }

  /** El backend devuelve el `FileOut` normal + `scan_status` (ver types.ts). */
  async complete(sessionId: string, parts: ConfirmedPart[]): Promise<FileOut> {
    const response = await axiosInstance.post<FileOut>(`${this.basePath}/${sessionId}/complete`, { parts })
    return response.data
  }

  async abort(sessionId: string): Promise<void> {
    await axiosInstance.post(`${this.basePath}/${sessionId}/abort`)
  }
}

export const uploadsService = new UploadsService()
