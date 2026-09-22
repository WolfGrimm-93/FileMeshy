/**
 * Texto/tono de estado de un `UploadItem`, compartido entre `UploadModal.tsx`
 * (lista dentro del modal) y `UploadsTray.tsx` (panel flotante global) --
 * para no duplicar (y potencialmente desincronizar) la lógica de "qué dice
 * cada estado" en dos componentes. El ícono y el layout de cada uno siguen
 * siendo propios de cada componente (son presentacionales, no lógica).
 */
import type { UploadItem, UploadItemStatus } from '../store/uploadsStore'

export type UploadStatusTone = 'neutral' | 'progress' | 'success' | 'warning' | 'danger'

export function uploadStatusLabel(item: UploadItem): string {
  switch (item.status) {
    case 'pending':
      return 'En cola...'
    case 'uploading':
      return `Subiendo — ${item.progress}%`
    case 'waiting_admission':
      return `Servidor ocupado con otras subidas grandes — reintentando en ~${item.retryAfterSeconds ?? '...'}s`
    case 'completing':
      return 'Finalizando...'
    case 'processing':
      return item.scanTimedOut
        ? 'No pudimos confirmar el resultado del escaneo de seguridad -- puede seguir en proceso'
        : 'Procesando (escaneo de seguridad)...'
    case 'paused':
      return `Pausada — ${item.error ?? 'una parte falló varias veces'}`
    case 'error':
      return item.error ?? 'Error al subir el archivo'
    case 'infected':
      // `item.error` trae el mensaje real redactado por el backend cuando la notificación
      // de av_scan.py lo resolvió (infectado o "no se pudo confirmar tras varios intentos") --
      // más preciso que un texto genérico, ver uploadsStore.ts::pollProcessingItems.
      return item.error ?? 'Removido: se detectó contenido malicioso en el escaneo de seguridad'
    case 'aborted':
      return 'Subida cancelada'
    case 'done':
      return 'Completado'
    default:
      return ''
  }
}

const TONE_BY_STATUS: Record<UploadItemStatus, UploadStatusTone> = {
  pending: 'neutral',
  uploading: 'progress',
  waiting_admission: 'warning',
  completing: 'progress',
  processing: 'progress',
  paused: 'warning',
  error: 'danger',
  infected: 'danger',
  aborted: 'neutral',
  done: 'success',
}

export function uploadStatusTone(item: UploadItem): UploadStatusTone {
  if (item.status === 'processing' && item.scanTimedOut) return 'warning'
  return TONE_BY_STATUS[item.status]
}

export function progressBarVariant(item: UploadItem): 'default' | 'success' | 'warning' | 'danger' | 'info' {
  switch (uploadStatusTone(item)) {
    case 'success':
      return 'success'
    case 'danger':
      return 'danger'
    case 'warning':
      return 'warning'
    case 'progress':
      return item.status === 'processing' || item.status === 'completing' ? 'info' : 'default'
    default:
      return 'default'
  }
}

/** Un item puede reintentarse a mano solo si es multipart y quedó pausado/errado
 *  con una sesión viva en el backend (`sessionId`). */
export function canRetryItem(item: UploadItem): boolean {
  return item.kind === 'multipart' && Boolean(item.sessionId) && (item.status === 'paused' || item.status === 'error')
}

/** Un item puede cancelarse mientras sigue "en vuelo" -- no tiene sentido abortar
 *  algo que ya terminó (done/infected/aborted) ni algo en escaneo (el archivo ya
 *  está subido, abortar ahí no tiene efecto útil en el backend). */
export function canAbortItem(item: UploadItem): boolean {
  return item.kind === 'multipart' && ['pending', 'uploading', 'waiting_admission', 'paused'].includes(item.status)
}
