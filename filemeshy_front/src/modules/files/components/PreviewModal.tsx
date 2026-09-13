/**
 * Preview inline de imágenes y PDF (Hito 2). Reusada tanto desde el
 * explorador autenticado (FilesPage) como desde la página pública de share
 * (PublicSharePage) — recibe la URL de descarga ya resuelta, no conoce nada
 * de permisos ni de sesión.
 */
import { Download } from 'lucide-react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'

export interface PreviewTarget {
  name: string
  mimeType: string
  downloadUrl: string
}

interface PreviewModalProps {
  target: PreviewTarget | null
  onClose: () => void
}

export default function PreviewModal({ target, onClose }: PreviewModalProps) {
  if (!target) return null

  const isImage = target.mimeType.startsWith('image/')
  const isPdf = target.mimeType === 'application/pdf'

  return (
    <Modal isOpen={!!target} onClose={onClose} title={target.name} size={isImage || isPdf ? '4xl' : 'md'}>
      {isImage && (
        <div className="flex items-center justify-center">
          <img
            src={target.downloadUrl}
            alt={target.name}
            className="max-h-[75vh] max-w-full rounded-sm object-contain"
          />
        </div>
      )}

      {isPdf && (
        <iframe
          src={target.downloadUrl}
          title={target.name}
          className="h-[75vh] w-full rounded-sm border border-gray-200 dark:border-gray-700"
        />
      )}

      {!isImage && !isPdf && (
        <div className="flex flex-col items-center gap-4 py-8 text-center">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Vista previa no disponible para este tipo de archivo.
          </p>
          <Button
            variant="primary"
            leftIcon={<Download className="size-4" />}
            onClick={() => {
              window.location.href = target.downloadUrl
            }}
          >
            Descargar
          </Button>
        </div>
      )}
    </Modal>
  )
}
