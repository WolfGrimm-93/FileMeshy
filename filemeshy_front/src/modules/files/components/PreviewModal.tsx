/**
 * Preview inline de imágenes, PDF (Hito 2), video, audio y documentos de
 * Office (Ronda 5). Reusada tanto desde el explorador autenticado
 * (FilesPage) como desde la página pública de share (PublicSharePage) --
 * recibe la URL de descarga ya resuelta, no conoce nada de permisos ni de
 * sesión.
 *
 * Office (docx/xlsx/pptx) es el único caso que necesita `fileId`: la
 * conversión a PDF la hace el backend bajo demanda (no cacheada la primera
 * vez, ver `filesService.getOfficePreviewUrl`), así que este componente
 * dispara ese request al abrir el modal y muestra un estado de carga
 * mientras espera. Si no viene `fileId` (caso de la página pública, que no
 * tiene un endpoint autenticado disponible) el tipo simplemente no se trata
 * como previsualizable y cae al fallback de "vista previa no disponible".
 */
import { useEffect, useState } from 'react'
import { Download, Loader2, Music } from 'lucide-react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'
import { filesService } from '../services/files.service'

export interface PreviewTarget {
  name: string
  mimeType: string
  downloadUrl: string
  /**
   * Id del archivo -- opcional porque solo hace falta para pedir el preview
   * de Office (`getOfficePreviewUrl`). Imagen/PDF/video/audio se resuelven
   * enteramente con `downloadUrl`, sin necesidad del id.
   */
  fileId?: string
}

interface PreviewModalProps {
  target: PreviewTarget | null
  onClose: () => void
}

const VIDEO_MIME_TYPES = new Set(['video/mp4', 'video/webm', 'video/ogg'])
const AUDIO_MIME_TYPES = new Set(['audio/mpeg', 'audio/wav', 'audio/ogg'])
const OFFICE_MIME_PREFIX = 'application/vnd.openxmlformats-officedocument.'

/** Timeout del lado del cliente para la conversión a PDF -- generoso porque
 * la primera conversión de un documento no está cacheada en el backend. */
const OFFICE_PREVIEW_TIMEOUT_MS = 40_000

type OfficePreviewState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; url: string }
  | { status: 'error' }

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Tiempo de espera agotado')), ms)
    promise.then(
      (value) => {
        clearTimeout(timer)
        resolve(value)
      },
      (error: unknown) => {
        clearTimeout(timer)
        reject(error)
      }
    )
  })
}

export default function PreviewModal({ target, onClose }: PreviewModalProps) {
  const isImage = !!target && target.mimeType.startsWith('image/')
  const isPdf = !!target && target.mimeType === 'application/pdf'
  const isVideo = !!target && VIDEO_MIME_TYPES.has(target.mimeType)
  const isAudio = !!target && AUDIO_MIME_TYPES.has(target.mimeType)
  const isOffice = !!target && target.mimeType.startsWith(OFFICE_MIME_PREFIX) && !!target.fileId

  const [officePreview, setOfficePreview] = useState<OfficePreviewState>({ status: 'idle' })

  useEffect(() => {
    // No hace falta resetear explícitamente a 'idle' acá: `officePreviewUrl`
    // y `showOfficeError` (más abajo) ya filtran por `isOffice`, así que un
    // `officePreview` obsoleto de un archivo de Office anterior queda inerte
    // en cuanto se abre un target que no es Office.
    if (!isOffice || !target?.fileId) return

    // Guard para descartar la respuesta si el modal se cerró o el target
    // cambió (usuario abrió otro archivo) antes de que resuelva el request --
    // evita pisar el estado de un preview distinto al que quedó en pantalla.
    let cancelled = false
    setOfficePreview({ status: 'loading' })

    withTimeout(filesService.getOfficePreviewUrl(target.fileId), OFFICE_PREVIEW_TIMEOUT_MS)
      .then((url) => {
        if (cancelled) return
        setOfficePreview({ status: 'ready', url })
      })
      .catch(() => {
        if (cancelled) return
        setOfficePreview({ status: 'error' })
      })

    return () => {
      cancelled = true
    }
  }, [target?.fileId, isOffice])

  if (!target) return null

  const officePreviewUrl = isOffice && officePreview.status === 'ready' ? officePreview.url : null
  // `!= null` (no `!== null`) a propósito: cubre tanto `null` como
  // `undefined`, más el chequeo de string no vacío. Un contrato de backend
  // que no coincida con el tipo declarado (bug real detectado en revisión
  // adversarial: el backend manda `preview_url`, no `url`) deja pasar
  // `undefined` como si fuera una URL válida con una comparación estricta
  // contra `null` -- combinado con que el bloque de fallback genérico
  // excluye a `isOffice`, el modal quedaba "listo" sin URL real: en blanco,
  // sin spinner ni mensaje de error. `officeReady` decide tanto el embed
  // como el estado de error de abajo, así que ese tipo de bug de contrato
  // cae siempre en el path de error visible en vez de un estado fantasma.
  const officeReady = officePreviewUrl != null && officePreviewUrl !== ''
  // El embed de PDF se reusa tal cual para el PDF convertido de Office --
  // misma pieza de UI, solo cambia de dónde sale la URL.
  const embedPdfUrl = isPdf ? target.downloadUrl : officeReady ? officePreviewUrl : null

  const isLargePreview = isImage || isPdf || isVideo || officeReady
  const showDownloadFallback = !isImage && !isPdf && !isVideo && !isAudio && !isOffice
  // Incluye el caso "ready pero sin URL usable" (contrato de backend roto o
  // cambiado) -- sin esto, ese estado no caía en ningún branch visible.
  const showOfficeError =
    isOffice && (officePreview.status === 'error' || (officePreview.status === 'ready' && !officeReady))

  const handleDownload = () => {
    window.location.href = target.downloadUrl
  }

  return (
    <Modal isOpen={!!target} onClose={onClose} title={target.name} size={isLargePreview ? '4xl' : 'md'}>
      {isImage && (
        <div className="flex items-center justify-center">
          <img
            src={target.downloadUrl}
            alt={target.name}
            className="max-h-[75vh] max-w-full rounded-sm object-contain"
          />
        </div>
      )}

      {embedPdfUrl && (
        <iframe
          src={embedPdfUrl}
          title={target.name}
          className="h-[75vh] w-full rounded-sm border border-gray-200 dark:border-gray-700"
        />
      )}

      {isVideo && (
        <video controls className="max-h-[70vh] w-full rounded-sm bg-black">
          <source src={target.downloadUrl} type={target.mimeType} />
        </video>
      )}

      {isAudio && (
        <div className="flex flex-col items-center gap-6 py-8">
          <div className="flex size-20 items-center justify-center rounded-full bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-600">
            <Music className="size-10" />
          </div>
          <audio controls className="w-full" src={target.downloadUrl} />
        </div>
      )}

      {isOffice && officePreview.status === 'loading' && (
        <div className="flex flex-col items-center gap-4 py-16 text-center">
          <Loader2 className="size-8 animate-spin text-brand-500" />
          <p className="text-sm text-gray-600 dark:text-gray-400">Generando vista previa...</p>
        </div>
      )}

      {showOfficeError && (
        <div className="flex flex-col items-center gap-4 py-8 text-center">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            No se pudo generar la vista previa de este documento.
          </p>
          <Button variant="primary" leftIcon={<Download className="size-4" />} onClick={handleDownload}>
            Descargar archivo original
          </Button>
        </div>
      )}

      {showDownloadFallback && (
        <div className="flex flex-col items-center gap-4 py-8 text-center">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Vista previa no disponible para este tipo de archivo.
          </p>
          <Button variant="primary" leftIcon={<Download className="size-4" />} onClick={handleDownload}>
            Descargar
          </Button>
        </div>
      )}
    </Modal>
  )
}
