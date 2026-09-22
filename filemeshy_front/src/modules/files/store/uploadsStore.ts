/**
 * Store global de subidas (Zustand) -- reemplaza el estado local que tenía
 * `useFileUpload.ts` para que una subida grande (multipart) SIGA en curso
 * aunque el usuario cierre el modal o navegue a otra página de la app (solo
 * se corta si cierra la pestaña/recarga -- eso lo cubre la reanudación vía
 * IndexedDB, ver `lib/uploadSessionsDb.ts`).
 *
 * Dos "carriles" conviven acá:
 *  - `kind: 'simple'`    -- archivos <=100MB, mismo `filesService.upload()`
 *    de siempre (Ronda 1), sin tocar su comportamiento.
 *  - `kind: 'multipart'` -- archivos >100MB, motor nuevo de
 *    `lib/multipartUploader.ts` + endpoints `/uploads/*` (ver
 *    `services/uploads.service.ts`).
 *
 * UI que consume esto: `hooks/useFileUpload.ts` (wrapper delgado, mantiene
 * la firma vieja para no romper `FilesPage.tsx`/`UploadModal.tsx`),
 * `components/UploadModal.tsx` (lista dentro del modal) y
 * `components/UploadsTray.tsx` (panel flotante global, sobrevive cierre del
 * modal -- montado una sola vez en `app/layout/MainLayout.tsx`).
 */
import { create } from 'zustand'
import { toast } from '@/ui/toast/CustomToast'
import { extractErrorMessage } from '@/shared/utils/errors'
import { filesService } from '../services/files.service'
import { notificationService, type Notification } from '@/modules/notifications/services/notification.service'
import { uploadsService, UploadAdmissionError, type InitiateUploadResponse } from '../services/uploads.service'
import {
  buildPartRanges,
  uploadPartsWithConcurrency,
  sleepAbortable,
  MultipartAbortedError,
  MultipartUploadPausedError,
  MULTIPART_THRESHOLD_BYTES,
  MAX_CONCURRENT_PARTS,
  MAX_PART_RETRIES,
} from '../lib/multipartUploader'
import {
  saveUploadSession,
  getUploadSession,
  deleteUploadSession,
  listUploadSessions,
  markPartConfirmed,
  type StoredUploadSession,
} from '../lib/uploadSessionsDb'
import type { FileOut } from '../types'

export { MULTIPART_THRESHOLD_BYTES }

/** Cada 8s (dentro del rango 5-10s pedido) mientras haya archivos en estado
 *  "procesando" (escaneo antivirus pendiente) visibles en algún panel. */
const SCAN_POLL_INTERVAL_MS = 8000

export type UploadItemStatus =
  | 'pending'
  | 'uploading'
  | 'waiting_admission'
  | 'completing'
  | 'processing'
  | 'paused'
  | 'done'
  | 'infected'
  | 'error'
  | 'aborted'

export interface UploadItem {
  id: string
  file: File
  fileName: string
  sizeBytes: number
  folderId: string | undefined
  kind: 'simple' | 'multipart'
  status: UploadItemStatus
  /** Porcentaje agregado 0-100, en bytes confirmados/total (no solo por parte). */
  progress: number
  error?: string
  sessionId?: string
  fileOut?: FileOut
  /** Solo con status 'waiting_admission' -- cuántos segundos falta para el próximo intento. */
  retryAfterSeconds?: number
  /** `Date.now()` de cuando el item pasó a 'processing' -- usado para el timeout de
   *  `scanTimedOut` de abajo (ver `pollProcessingItems`). */
  processingSince?: number
  /** Se pone en `true` si `status === 'processing'` lleva demasiado tiempo sin resolver
   *  Y el backend además dejó de responder 200 en `GET /files/{id}` -- ESO ES AMBIGUO por
   *  diseño (ver comentario grande en `pollProcessingItems`): puede ser que siga escaneando
   *  un archivo gigante, o que ya lo haya marcado 'infected' y lo esté ocultando. No lo
   *  presentamos como "infectado" (sería una afirmación falsa la mayoría de las veces),
   *  solo avisamos que no pudimos confirmar el resultado. */
  scanTimedOut?: boolean
  /** Capturado al iniciar la subida -- se vuelve a invocar cuando el escaneo
   *  termina en 'clean', porque ES el momento real en que el archivo pasa a
   *  aparecer en `GET /files` normal (antes de eso el backend lo filtra). */
  onUploaded?: (file: FileOut) => void
}

interface UploadsState {
  items: UploadItem[]
  resumableSessions: StoredUploadSession[]
  uploadFiles: (files: File[], folderId: string | undefined, onUploaded: (file: FileOut) => void) => void
  retryItem: (id: string) => void
  abortItem: (id: string) => void
  dismissItem: (id: string) => void
  scanForResumableSessions: () => Promise<void>
  resumeSession: (sessionId: string, file: File, onUploaded: (file: FileOut) => void) => Promise<void>
  discardResumableSession: (sessionId: string) => Promise<void>
}

// ---------------------------------------------------------------------------
// Estado mutable "de motor" que NO vive en Zustand a propósito -- no es UI
// (no debe disparar re-render) y no es serializable de forma útil
// (AbortController, Map de URLs firmadas vivas en memoria).
// ---------------------------------------------------------------------------
const abortControllers = new Map<string, AbortController>()
const activePartUrls = new Map<string, Map<number, string>>()
let scanPollTimer: ReturnType<typeof setInterval> | null = null

function generateItemId(file: File): string {
  return `${file.name}-${file.size}-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function getResponseStatus(error: unknown): number | undefined {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { status?: number } }).response
    return response?.status
  }
  return undefined
}

export const useUploadsStore = create<UploadsState>((set, get) => ({
  items: [],
  resumableSessions: [],

  uploadFiles: (files, folderId, onUploaded) => {
    for (const file of files) {
      const id = generateItemId(file)
      const kind: UploadItem['kind'] = file.size > MULTIPART_THRESHOLD_BYTES ? 'multipart' : 'simple'
      const item: UploadItem = {
        id,
        file,
        fileName: file.name,
        sizeBytes: file.size,
        folderId,
        kind,
        status: 'pending',
        progress: 0,
        onUploaded,
      }
      set((state) => ({ items: [...state.items, item] }))
      if (kind === 'simple') {
        void startSimpleUpload(id)
      } else {
        void startMultipartUpload(id)
      }
    }
  },

  retryItem: (id) => {
    void retryMultipartItem(id)
  },

  abortItem: (id) => {
    void abortItemInternal(id)
  },

  dismissItem: (id) => set((state) => ({ items: state.items.filter((i) => i.id !== id) })),

  scanForResumableSessions: async () => {
    const sessions = await listUploadSessions()
    const activeIds = new Set(get().items.map((i) => i.sessionId).filter((v): v is string => Boolean(v)))
    set({ resumableSessions: sessions.filter((s) => !activeIds.has(s.sessionId)) })
  },

  resumeSession: async (sessionId, file, onUploaded) => {
    await resumeSessionInternal(sessionId, file, onUploaded)
  },

  discardResumableSession: async (sessionId) => {
    try {
      await uploadsService.abort(sessionId)
    } catch {
      // Best-effort -- la sesión puede haber vencido en el backend igual, lo que importa
      // es que desaparezca de acá.
    }
    await deleteUploadSession(sessionId)
    set((state) => ({ resumableSessions: state.resumableSessions.filter((s) => s.sessionId !== sessionId) }))
  },
}))

// ---------------------------------------------------------------------------
// Helpers de acceso al store desde funciones fuera de `create()` (patrón
// estándar de Zustand para lógica async larga que no conviene inline).
// ---------------------------------------------------------------------------

function getItem(id: string): UploadItem | undefined {
  return useUploadsStore.getState().items.find((i) => i.id === id)
}

function updateItem(id: string, patch: Partial<UploadItem>): void {
  useUploadsStore.setState((state) => ({
    items: state.items.map((i) => (i.id === id ? { ...i, ...patch } : i)),
  }))
}

function addItem(item: UploadItem): void {
  useUploadsStore.setState((state) => ({ items: [...state.items, item] }))
}

function removeItem(id: string): void {
  useUploadsStore.setState((state) => ({ items: state.items.filter((i) => i.id !== id) }))
}

// ---------------------------------------------------------------------------
// Camino simple (<=100MB) -- mismo `filesService.upload()` de siempre, solo
// que ahora reportando a este store en vez de a un `useState` local. Cero
// cambio de comportamiento respecto al `useFileUpload.ts` original.
// ---------------------------------------------------------------------------

async function startSimpleUpload(id: string): Promise<void> {
  const item = getItem(id)
  if (!item) return
  updateItem(id, { status: 'uploading' })
  try {
    const uploaded = await filesService.upload(item.file, item.folderId, (percent) => {
      updateItem(id, { progress: percent })
    })
    updateItem(id, { status: 'done', progress: 100, fileOut: uploaded })
    item.onUploaded?.(uploaded)
  } catch (error: unknown) {
    const message = extractErrorMessage(error, 'Error al subir el archivo')
    updateItem(id, { status: 'error', error: message })
    toast.error(`${item.file.name}: ${message}`)
  }
}

// ---------------------------------------------------------------------------
// Camino multipart (>100MB)
// ---------------------------------------------------------------------------

/** Tope de reintentos automáticos ante un 503 de `/initiate` -- ver el comentario grande
 *  en `uploads.service.ts::initiate` sobre por qué esto ya NO puede confiar en la
 *  presencia de `Retry-After` para distinguir "esperá tu turno" de "la infra está
 *  caída": hoy ese header no llega nunca, así que cualquier 503 se trata como
 *  candidato a admission control. Sin este tope, una falla de infra genuina (MinIO
 *  caído) dejaría el item reintentando para siempre en vez de convertirse en un error
 *  accionable. Con el backoff de abajo (5,10,15,20,25,30,30,30s) son ~2m45s de
 *  reintentos antes de rendirse -- de sobra para que la admission-control real
 *  (transitoria, gente subiendo archivos grandes a la vez) se libere sola. */
const MAX_ADMISSION_RETRIES = 8

async function initiateWithAdmissionRetry(
  itemId: string,
  file: File,
  folderId: string | undefined,
  signal: AbortSignal
): Promise<InitiateUploadResponse | null> {
  let attempt = 0
  while (true) {
    if (signal.aborted) return null
    try {
      return await uploadsService.initiate({
        file_name: file.name,
        size_bytes: file.size,
        mime_type: file.type || 'application/octet-stream',
        folder_id: folderId,
      })
    } catch (error) {
      if (error instanceof UploadAdmissionError) {
        attempt++
        if (attempt > MAX_ADMISSION_RETRIES) {
          throw new Error(
            'El servidor sigue ocupado con otras subidas grandes después de varios intentos -- probá de nuevo en unos minutos'
          )
        }
        const waitSeconds = error.retryAfterSeconds ?? Math.min(30, 5 * attempt)
        updateItem(itemId, { status: 'waiting_admission', retryAfterSeconds: waitSeconds })
        if (attempt === 1) {
          toast.info('El servidor está ocupado con otras subidas grandes, reintentando automáticamente...')
        }
        await sleepAbortable(waitSeconds * 1000, signal)
        continue
      }
      throw error
    }
  }
}

/** Recorre las partes pendientes de `sessionId` (leyendo lo ya confirmado desde
 *  IndexedDB) y, al terminar todas, llama `/complete`. Compartido por el arranque
 *  en frío, el reintento manual y la reanudación tras reload -- las tres rutas
 *  llegan acá con la sesión ya creada/confirmada en el backend y sus URLs vivas
 *  en `activePartUrls`. */
async function runPartsAndComplete(
  itemId: string,
  file: File,
  sessionId: string,
  parts: ReturnType<typeof buildPartRanges>,
  signal: AbortSignal
): Promise<void> {
  const stored = await getUploadSession(sessionId)
  const confirmedEtags = new Map<number, string>()
  if (stored) {
    for (const [partNumberStr, etag] of Object.entries(stored.confirmedParts)) {
      confirmedEtags.set(Number(partNumberStr), etag)
    }
  }

  const partSizeByNumber = new Map(parts.map((p) => [p.partNumber, p.size]))
  const inFlightLoaded = new Map<number, number>()
  const totalBytes = file.size

  function recomputeProgress(): void {
    let confirmedBytes = 0
    for (const partNumber of confirmedEtags.keys()) confirmedBytes += partSizeByNumber.get(partNumber) ?? 0
    let inflightBytes = 0
    for (const [partNumber, loaded] of inFlightLoaded.entries()) {
      if (!confirmedEtags.has(partNumber)) inflightBytes += loaded
    }
    const percent = totalBytes === 0 ? 100 : Math.min(100, Math.round(((confirmedBytes + inflightBytes) / totalBytes) * 100))
    updateItem(itemId, { progress: percent })
  }
  recomputeProgress()

  updateItem(itemId, { status: 'uploading' })

  await uploadPartsWithConcurrency({
    file,
    parts,
    alreadyConfirmed: new Set(confirmedEtags.keys()),
    getUrl: (partNumber) => activePartUrls.get(itemId)?.get(partNumber),
    refreshUrls: async () => {
      const refreshed = await uploadsService.refreshPartUrls(sessionId)
      const urlMap = activePartUrls.get(itemId) ?? new Map<number, string>()
      for (const p of refreshed.part_urls) urlMap.set(p.part_number, p.url)
      activePartUrls.set(itemId, urlMap)
      for (const confirmed of refreshed.completed_parts) {
        if (!confirmedEtags.has(confirmed.part_number)) {
          confirmedEtags.set(confirmed.part_number, confirmed.etag)
          void markPartConfirmed(sessionId, confirmed.part_number, confirmed.etag)
        }
      }
      recomputeProgress()
    },
    concurrency: MAX_CONCURRENT_PARTS,
    maxRetries: MAX_PART_RETRIES,
    signal,
    onPartProgress: (partNumber, loaded) => {
      inFlightLoaded.set(partNumber, loaded)
      recomputeProgress()
    },
    onPartConfirmed: (partNumber, etag) => {
      confirmedEtags.set(partNumber, etag)
      inFlightLoaded.delete(partNumber)
      recomputeProgress()
      void markPartConfirmed(sessionId, partNumber, etag)
    },
  })

  updateItem(itemId, { status: 'completing', progress: 100 })
  const orderedParts = [...confirmedEtags.entries()]
    .sort(([a], [b]) => a - b)
    .map(([part_number, etag]) => ({ part_number, etag }))

  const fileOut = await uploadsService.complete(sessionId, orderedParts)
  await deleteUploadSession(sessionId)
  abortControllers.delete(itemId)
  activePartUrls.delete(itemId)

  const item = getItem(itemId)
  if (fileOut.scan_status === 'pending') {
    updateItem(itemId, { status: 'processing', fileOut, processingSince: Date.now() })
    item?.onUploaded?.(fileOut)
    ensureScanPolling()
  } else {
    updateItem(itemId, { status: 'done', progress: 100, fileOut })
    item?.onUploaded?.(fileOut)
  }
}

function handleMultipartError(itemId: string, error: unknown): void {
  abortControllers.delete(itemId)
  if (error instanceof MultipartAbortedError) {
    updateItem(itemId, { status: 'aborted' })
    return
  }
  if (error instanceof MultipartUploadPausedError) {
    updateItem(itemId, { status: 'paused', error: error.message })
    toast.warning(`Subida pausada -- ${error.message}. Podés reintentar cuando quieras.`)
    return
  }
  const message = extractErrorMessage(error, 'Error al subir el archivo')
  updateItem(itemId, { status: 'error', error: message })
  toast.error(message)
}

async function startMultipartUpload(itemId: string): Promise<void> {
  const item = getItem(itemId)
  if (!item) return

  const controller = new AbortController()
  abortControllers.set(itemId, controller)

  try {
    const initiated = await initiateWithAdmissionRetry(itemId, item.file, item.folderId, controller.signal)
    if (!initiated) return // abortado mientras esperaba admisión

    const { upload_session_id: sessionId, part_urls, part_size_bytes } = initiated
    const parts = buildPartRanges(item.file.size, part_size_bytes)
    activePartUrls.set(itemId, new Map(part_urls.map((p) => [p.part_number, p.url])))

    await saveUploadSession({
      sessionId,
      fileName: item.file.name,
      sizeBytes: item.file.size,
      mimeType: item.file.type || 'application/octet-stream',
      folderId: item.folderId,
      partSizeBytes: part_size_bytes,
      totalParts: parts.length,
      confirmedParts: {},
      createdAt: Date.now(),
      updatedAt: Date.now(),
    })
    updateItem(itemId, { sessionId })

    await runPartsAndComplete(itemId, item.file, sessionId, parts, controller.signal)
  } catch (error) {
    handleMultipartError(itemId, error)
  }
}

/** Reintento manual de un item 'paused'/'error' -- el `File` original sigue vivo en
 *  memoria (no hubo reload de página), así que no hace falta pedirle nada al usuario:
 *  solo refrescar URLs (pueden haber vencido durante la pausa) y seguir. */
async function retryMultipartItem(itemId: string): Promise<void> {
  const item = getItem(itemId)
  if (!item || item.kind !== 'multipart' || !item.sessionId) return

  const stored = await getUploadSession(item.sessionId)
  if (!stored) {
    updateItem(itemId, { status: 'error', error: 'La sesión de subida ya no existe -- iniciá la subida de nuevo' })
    return
  }

  updateItem(itemId, { status: 'uploading', error: undefined })
  const controller = new AbortController()
  abortControllers.set(itemId, controller)

  try {
    const refreshed = await uploadsService.refreshPartUrls(item.sessionId)
    const urlMap = activePartUrls.get(itemId) ?? new Map<number, string>()
    for (const p of refreshed.part_urls) urlMap.set(p.part_number, p.url)
    activePartUrls.set(itemId, urlMap)
    for (const confirmed of refreshed.completed_parts) {
      await markPartConfirmed(item.sessionId, confirmed.part_number, confirmed.etag)
    }

    const parts = buildPartRanges(item.sizeBytes, stored.partSizeBytes)
    await runPartsAndComplete(itemId, item.file, item.sessionId, parts, controller.signal)
  } catch (error) {
    handleMultipartError(itemId, error)
  }
}

async function abortItemInternal(itemId: string): Promise<void> {
  const item = getItem(itemId)
  if (!item) return

  abortControllers.get(itemId)?.abort()
  abortControllers.delete(itemId)
  activePartUrls.delete(itemId)

  if (item.kind === 'multipart' && item.sessionId) {
    try {
      await uploadsService.abort(item.sessionId)
    } catch {
      // Best-effort -- igual la borramos localmente.
    }
    await deleteUploadSession(item.sessionId)
  }
  removeItem(itemId)
}

// ---------------------------------------------------------------------------
// Reanudación tras reload/reinicio -- el usuario tuvo que volver a seleccionar
// el archivo (el browser no puede releer un File del que perdió la
// referencia), la UI (`UploadsTray.tsx`) ya validó nombre+tamaño antes de
// llamar acá, pero se revalida igual por las dudas.
// ---------------------------------------------------------------------------

async function resumeSessionInternal(
  sessionId: string,
  file: File,
  onUploaded: (file: FileOut) => void
): Promise<void> {
  const stored = await getUploadSession(sessionId)
  if (!stored) {
    toast.error('Esa sesión de subida ya no existe')
    return
  }
  if (stored.fileName !== file.name || stored.sizeBytes !== file.size) {
    toast.error('El archivo seleccionado no coincide con el de la subida guardada (nombre o tamaño distinto)')
    return
  }

  const itemId = generateItemId(file)
  addItem({
    id: itemId,
    file,
    fileName: file.name,
    sizeBytes: file.size,
    folderId: stored.folderId,
    kind: 'multipart',
    status: 'uploading',
    progress: 0,
    sessionId,
    onUploaded,
  })
  useUploadsStore.setState((state) => ({
    resumableSessions: state.resumableSessions.filter((s) => s.sessionId !== sessionId),
  }))

  const controller = new AbortController()
  abortControllers.set(itemId, controller)

  try {
    const refreshed = await uploadsService.refreshPartUrls(sessionId)
    activePartUrls.set(itemId, new Map(refreshed.part_urls.map((p) => [p.part_number, p.url])))
    for (const confirmed of refreshed.completed_parts) {
      await markPartConfirmed(sessionId, confirmed.part_number, confirmed.etag)
    }

    const parts = buildPartRanges(stored.sizeBytes, stored.partSizeBytes)
    await runPartsAndComplete(itemId, file, sessionId, parts, controller.signal)
  } catch (error) {
    handleMultipartError(itemId, error)
  }
}

// ---------------------------------------------------------------------------
// Resolución de "procesando" -- señal PRIMARIA: notificaciones.
//
// Se evaluó reusar el polling de notificaciones (`Navbar.tsx`, cada 30s
// sobre `/notifications/unread-count`) y terminó siendo la señal correcta,
// pero no por acoplarse a ESE poll -- confirmado leyendo
// `filemeshy_back/app/worker/tasks/av_scan.py` (la tarea async de escaneo,
// código real de otro agente de esta ronda, terminada mientras se escribía
// este archivo): al resolver, crea una `Notification` con
// `extra_data.file_id` + `severity` ('success' un archivo limpio, 'error'
// infectado, 'warning' si el AV no pudo confirmar tras varios reintentos) --
// exactamente el evento que faltaba para no tener que adivinar. Poll propio
// (no el de `Navbar.tsx`, que solo trae el conteo) cada `SCAN_POLL_INTERVAL_MS`
// contra `GET /notifications`, UNA sola llamada por tick que cubre todos los
// items 'processing' a la vez.
//
// Señal SECUNDARIA (fallback): `GET /files/{id}` directo -- puede resolver
// 'clean' más rápido si por lo que sea la notificación se demora. OJO (leyendo
// `app/files/repository.py::CRUDFile.get/get_active`, mismo agente): el
// filtro `scan_status == 'clean'` es GLOBAL para toda lectura por id -- ni el
// dueño puede leer un archivo 'pending'/'infected'/'scan_failed' por ahí, da
// 404 en los tres casos por igual. Por eso esta señal SOLO puede confirmar
// 'clean' (200), nunca "infectado" (sería adivinar sobre un 404 ambiguo --
// hallazgo de una revisión propia antes de integrar contra el contrato real,
// versión anterior de este archivo SÍ lo hacía mal).
//
// Red de seguridad final: si ninguna de las dos señales resolvió en
// `PENDING_SCAN_INCONCLUSIVE_AFTER_MS`, se avisa la incertidumbre en vez de
// mentir ("listo" o "infectado" serían ambos una afirmación falsa posible).
// ---------------------------------------------------------------------------

const PENDING_SCAN_INCONCLUSIVE_AFTER_MS = 30 * 60 * 1000

function ensureScanPolling(): void {
  if (scanPollTimer) return
  scanPollTimer = setInterval(() => {
    void pollProcessingItems()
  }, SCAN_POLL_INTERVAL_MS)
}

/** `extra_data` es `Record<string, unknown> | null` en el tipo de Notification -- este
 *  helper valida que `file_id` sea realmente un string antes de comparar, en vez de
 *  castear a ciegas. */
function notificationFileId(notification: Notification): string | undefined {
  const value = notification.extra_data?.file_id
  return typeof value === 'string' ? value : undefined
}

async function pollProcessingItems(): Promise<void> {
  const allProcessing = useUploadsStore.getState().items.filter((i) => i.status === 'processing' && i.fileOut)
  if (allProcessing.length === 0) {
    if (scanPollTimer) {
      clearInterval(scanPollTimer)
      scanPollTimer = null
    }
    return
  }

  let recentNotifications: Notification[] = []
  try {
    recentNotifications = (await notificationService.getNotifications({ page: 1, page_size: 20 })).items
  } catch {
    // Si falla, seguimos solo con la señal secundaria (GET /files/{id}) más abajo.
  }

  for (const item of allProcessing) {
    if (!item.fileOut) continue
    const fileId = item.fileOut.id

    const match = recentNotifications.find((n) => notificationFileId(n) === fileId)
    if (match) {
      if (match.severity === 'success') {
        const fresh = { ...item.fileOut, scan_status: 'clean' as const }
        updateItem(item.id, { status: 'done', fileOut: fresh })
        item.onUploaded?.(fresh)
        toast.success(match.message)
        continue
      }
      if (match.severity === 'error' || match.severity === 'warning') {
        // 'error' = infectado real, 'warning' = el AV no pudo confirmar tras varios
        // reintentos (`_notify_scan_needs_attention`) -- distintos motivos, mismo
        // resultado para el usuario (el archivo no está disponible), por eso comparten
        // el status 'infected'; el mensaje real (`match.message`, redactado por el
        // backend) es el que se muestra, no un texto genérico -- ver
        // `uploadStatusLabel` en lib/uploadItemPresentation.ts (usa `item.error` si
        // está seteado).
        updateItem(item.id, { status: 'infected', fileOut: item.fileOut, error: match.message })
        toast.error(match.message)
        continue
      }
    }

    // Sin notificación todavía -- señal secundaria: GET /files/{id} directo, que
    // SOLO puede confirmar 'clean' (200), ver comentario grande de arriba.
    try {
      const fresh = await filesService.get(fileId)
      updateItem(item.id, { status: 'done', fileOut: fresh })
      item.onUploaded?.(fresh)
      toast.success(`${fresh.name}: escaneo de seguridad completado, ya está disponible.`)
    } catch (error) {
      if (getResponseStatus(error) !== 404) continue // error transitorio -- reintenta en el próximo tick
      if (item.scanTimedOut) continue // ya se avisó la incertidumbre una vez, no repetir el toast
      const since = item.processingSince ?? Date.now()
      if (Date.now() - since > PENDING_SCAN_INCONCLUSIVE_AFTER_MS) {
        updateItem(item.id, { scanTimedOut: true })
        toast.warning(
          `${item.fileName}: no pudimos confirmar el resultado del escaneo de seguridad después de un buen rato. ` +
            'Puede seguir procesándose o haber sido removido -- si no aparece en tu listado más tarde, subilo de nuevo.'
        )
      }
      // Dentro del plazo -- 404 esperado mientras sigue 'pending', se reintenta en el próximo tick.
    }
  }
}
