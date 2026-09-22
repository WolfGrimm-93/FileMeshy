/**
 * Motor de subida por partes (multipart) directo del navegador a MinIO.
 *
 * No conoce React ni el store -- son funciones puras/casi-puras que reciben
 * callbacks, para poder testearlas aisladas (split de rangos, reintento,
 * concurrencia) sin necesidad del backend real ni de un DOM completo. La
 * orquestación de alto nivel (llamar a `/initiate`, guardar en IndexedDB,
 * decidir cuándo pausar) vive en `store/uploadsStore.ts`.
 *
 * Mismo estilo que `shared/utils/downloadFile.ts` (el precedente más
 * parecido en el repo: transferencia grande por partes, con reintento y
 * progreso agregado) -- backoff exponencial simple, sin librería nueva.
 */

/** Mismo límite que `MAX_UPLOAD_SIZE_MB` en `filemeshy_back/app/core/config.py` (100MB). Por
 *  encima de esto, un archivo usa el camino resumable en vez de `POST /files/upload`. */
export const MULTIPART_THRESHOLD_BYTES = 100 * 1024 * 1024

/** Partes en simultáneo -- no todas a la vez, para no saturar la conexión ni abrir
 *  cientos de sockets con un archivo de muchos GB. */
export const MAX_CONCURRENT_PARTS = 4

/** Reintentos por parte individual antes de pausar la subida completa. */
export const MAX_PART_RETRIES = 3

const RETRY_BASE_DELAY_MS = 1000

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** Espera `ms` pero se corta antes si `signal` se aborta (ej. usuario cancela
 *  mientras el motor está esperando el backoff de un admission-control 503). */
export function sleepAbortable(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve()
      return
    }
    const timer = setTimeout(() => {
      cleanup()
      resolve()
    }, ms)
    const onAbort = () => {
      cleanup()
      resolve()
    }
    function cleanup() {
      clearTimeout(timer)
      signal.removeEventListener('abort', onAbort)
    }
    signal.addEventListener('abort', onAbort)
  })
}

// ---------------------------------------------------------------------------
// Split del archivo en rangos de bytes (File.slice() es perezoso -- no lee
// el archivo a memoria, el browser lo hace on-demand al mandar cada parte).
// ---------------------------------------------------------------------------

export interface PartRange {
  partNumber: number
  start: number
  end: number
  size: number
}

export function buildPartRanges(fileSize: number, partSizeBytes: number): PartRange[] {
  const ranges: PartRange[] = []
  let start = 0
  let partNumber = 1
  while (start < fileSize) {
    const end = Math.min(start + partSizeBytes, fileSize)
    ranges.push({ partNumber, start, end, size: end - start })
    start = end
    partNumber++
  }
  return ranges
}

// ---------------------------------------------------------------------------
// Errores tipados -- distinguen "hay que refrescar la URL y reintentar ya"
// de "reintento normal con backoff" y de "el usuario canceló/pausó".
// ---------------------------------------------------------------------------

export class MultipartAbortedError extends Error {
  constructor() {
    super('Subida cancelada')
    this.name = 'MultipartAbortedError'
  }
}

export class PartUrlExpiredError extends Error {
  partNumber: number

  constructor(partNumber: number) {
    super(`La URL firmada de la parte ${partNumber} venció (403)`)
    this.name = 'PartUrlExpiredError'
    this.partNumber = partNumber
  }
}

/** La parte agotó sus reintentos -- señal para que el store pause TODA la subida
 *  (no solo esta parte) y deje el reintento manual al usuario, en vez de fallar
 *  el archivo completo en silencio. */
export class MultipartUploadPausedError extends Error {
  partNumber: number

  constructor(partNumber: number, reason: string) {
    super(`Parte ${partNumber} falló después de varios reintentos: ${reason}`)
    this.name = 'MultipartUploadPausedError'
    this.partNumber = partNumber
  }
}

// ---------------------------------------------------------------------------
// PUT crudo de una parte contra la URL presignada. XMLHttpRequest (no fetch)
// a propósito -- es lo único con progreso real de subida en el browser hoy
// (mismo motivo por el que `files.service.ts` usa axios/XHR y no fetch para
// `onUploadProgress`). Nunca lleva JWT ni cookies: la firma va en el query
// string de la URL, mandar credenciales de más solo puede romper CORS.
// ---------------------------------------------------------------------------

export function uploadPartXhr(
  url: string,
  blob: Blob,
  onLoaded: (loadedBytes: number) => void,
  signal: AbortSignal
): Promise<string> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new MultipartAbortedError())
      return
    }

    const xhr = new XMLHttpRequest()
    xhr.open('PUT', url)

    const onAbortSignal = () => xhr.abort()
    signal.addEventListener('abort', onAbortSignal)

    const cleanup = () => signal.removeEventListener('abort', onAbortSignal)

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onLoaded(event.loaded)
    }

    xhr.onload = () => {
      cleanup()
      if (xhr.status >= 200 && xhr.status < 300) {
        const etagHeader = xhr.getResponseHeader('ETag')
        if (!etagHeader) {
          reject(
            new Error(
              'La respuesta de MinIO no incluyó el header ETag (revisar que el proxy nginx exponga ' +
                '"Access-Control-Expose-Headers: ETag" -- sin él el browser lo recibe pero JS no puede leerlo)'
            )
          )
          return
        }
        resolve(etagHeader.replaceAll('"', ''))
        return
      }
      if (xhr.status === 403) {
        reject(new PartUrlExpiredError(-1))
        return
      }
      reject(new Error(`HTTP ${xhr.status} al subir la parte`))
    }

    xhr.onerror = () => {
      cleanup()
      reject(new Error('Error de red al subir la parte'))
    }

    xhr.onabort = () => {
      cleanup()
      reject(new MultipartAbortedError())
    }

    xhr.send(blob)
  })
}

// ---------------------------------------------------------------------------
// Cola con concurrencia limitada + reintento por parte + refresh de URL
// vencida. `getUrl`/`refreshUrls` son inyectados por el store: éste es el
// dueño del mapa mutable de URLs (necesita persistir en IndexedDB cuando
// cambian), acá solo se leen/piden actualizar.
// ---------------------------------------------------------------------------

export interface UploadPartsOptions {
  file: File
  parts: PartRange[]
  /** Partes que YA están confirmadas (reanudación) -- se saltean por completo. */
  alreadyConfirmed: Set<number>
  getUrl: (partNumber: number) => string | undefined
  /** Pide URLs nuevas al backend (refresh-part-urls) y actualiza el mapa que lee `getUrl`. */
  refreshUrls: () => Promise<void>
  concurrency: number
  maxRetries: number
  signal: AbortSignal
  onPartProgress: (partNumber: number, loadedBytes: number) => void
  onPartConfirmed: (partNumber: number, etag: string) => void
}

export async function uploadPartsWithConcurrency(options: UploadPartsOptions): Promise<void> {
  const { file, parts, alreadyConfirmed, getUrl, refreshUrls, concurrency, maxRetries, signal, onPartProgress, onPartConfirmed } =
    options

  const pending = parts.filter((p) => !alreadyConfirmed.has(p.partNumber))
  let cursor = 0
  let firstError: MultipartUploadPausedError | MultipartAbortedError | null = null

  async function worker(): Promise<void> {
    while (true) {
      if (signal.aborted || firstError) return
      const i = cursor++
      if (i >= pending.length) return
      const part = pending[i]
      const blob = file.slice(part.start, part.end)

      let attempt = 0
      let alreadyRefreshedForThisPart = false

      while (true) {
        if (signal.aborted) {
          firstError = new MultipartAbortedError()
          return
        }
        const url = getUrl(part.partNumber)
        if (!url) {
          // No debería pasar (refreshUrls ya se llamó cuando hacía falta), pero
          // sin URL no hay forma de seguir -- pausar en vez de reintentar en loop.
          firstError = new MultipartUploadPausedError(part.partNumber, 'No hay URL firmada disponible para esta parte')
          return
        }

        try {
          const etag = await uploadPartXhr(url, blob, (loaded) => onPartProgress(part.partNumber, loaded), signal)
          onPartConfirmed(part.partNumber, etag)
          break
        } catch (error) {
          if (error instanceof MultipartAbortedError) {
            firstError = error
            return
          }
          if (error instanceof PartUrlExpiredError && !alreadyRefreshedForThisPart) {
            alreadyRefreshedForThisPart = true
            try {
              await refreshUrls()
            } catch {
              // Si el refresh en sí falla, cae al camino de reintento normal de abajo
              // (cuenta como intento fallido, con backoff).
            }
            continue
          }

          attempt++
          if (attempt > maxRetries) {
            firstError = new MultipartUploadPausedError(
              part.partNumber,
              error instanceof Error ? error.message : 'Error desconocido'
            )
            return
          }
          onPartProgress(part.partNumber, 0) // resetear la barra de esa parte antes de reintentar
          await sleep(RETRY_BASE_DELAY_MS * 2 ** (attempt - 1))
        }
      }
    }
  }

  const workerCount = Math.min(concurrency, pending.length) || 1
  await Promise.all(Array.from({ length: workerCount }, () => worker()))

  if (firstError) throw firstError
}
