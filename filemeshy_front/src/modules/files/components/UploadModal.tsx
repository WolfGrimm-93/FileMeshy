import {
  CheckCircle2,
  XCircle,
  File as FileIcon,
  Clock,
  Loader2,
  ShieldAlert,
  RotateCcw,
  X,
  Ban,
} from 'lucide-react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'
import { Progress } from '@/ui/progress/Progress'
import { Badge } from '@/ui/badges/Badge'
import { FileUpload } from '@/ui/file-upload/FileUpload'
import { formatBytes } from '@/shared/utils/downloadFile'
import { useFileUpload } from '../hooks/useFileUpload'
import { uploadStatusLabel, progressBarVariant, canRetryItem, canAbortItem } from '../lib/uploadItemPresentation'
import type { UploadItem } from '../store/uploadsStore'
import type { FileOut } from '../types'

interface UploadModalProps {
  isOpen: boolean
  onClose: () => void
  folderId: string | undefined
  onUploaded: (file: FileOut) => void
}

function statusIcon(item: UploadItem) {
  switch (item.status) {
    case 'done':
      return <CheckCircle2 className="size-4 text-green-500 shrink-0" />
    case 'error':
      return <XCircle className="size-4 text-red-500 shrink-0" />
    case 'infected':
      return <ShieldAlert className="size-4 text-red-500 shrink-0" />
    case 'aborted':
      return <Ban className="size-4 text-gray-400 shrink-0" />
    case 'paused':
      return <XCircle className="size-4 text-yellow-500 shrink-0" />
    case 'waiting_admission':
      return <Clock className="size-4 text-yellow-500 shrink-0" />
    case 'processing':
    case 'completing':
      return <Loader2 className="size-4 text-brand-500 shrink-0 animate-spin" />
    default:
      return <FileIcon className="size-4 text-gray-400 shrink-0" />
  }
}

export default function UploadModal({ isOpen, onClose, folderId, onUploaded }: UploadModalProps) {
  const { items, isUploading, uploadFiles, resetItems, retryItem, abortItem } = useFileUpload(folderId, onUploaded)

  const handleClose = () => {
    if (isUploading) return
    resetItems()
    onClose()
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Subir archivos"
      size="lg"
      closeOnOverlayClick={!isUploading}
      showCloseButton={!isUploading}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={handleClose} disabled={isUploading}>
            {isUploading ? 'Subiendo...' : 'Cerrar'}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {/* Sin maxSize: sin tope de cliente; la validación real la hacen el backend y el routing simple/multipart de uploadsStore */}
        <FileUpload multiple onFilesSelected={uploadFiles} />

        {items.length > 0 && (
          <ul className="space-y-3 max-h-96 overflow-y-auto">
            {items.map((item) => {
              const canRetry = canRetryItem(item)
              const canAbort = canAbortItem(item)

              return (
                <li key={item.id} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                  <div className="flex items-center gap-2 mb-2">
                    {statusIcon(item)}
                    <span className="flex-1 truncate text-sm font-medium text-gray-900 dark:text-white">
                      {item.fileName}
                    </span>
                    {item.kind === 'multipart' && (
                      <Badge variant="gray" size="xs">
                        subida por partes
                      </Badge>
                    )}
                    <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">
                      {formatBytes(item.sizeBytes)}
                    </span>
                    {canRetry && (
                      <button
                        type="button"
                        title="Reintentar"
                        onClick={() => retryItem(item.id)}
                        className="shrink-0 text-brand-600 hover:text-brand-700 dark:text-brand-400"
                      >
                        <RotateCcw className="size-4" />
                      </button>
                    )}
                    {canAbort && (
                      <button
                        type="button"
                        title="Cancelar subida"
                        onClick={() => abortItem(item.id)}
                        className="shrink-0 text-gray-400 hover:text-red-600 dark:hover:text-red-400"
                      >
                        <X className="size-4" />
                      </button>
                    )}
                  </div>

                  {item.status === 'error' || item.status === 'paused' || item.status === 'infected' ? (
                    <p
                      className={`text-xs ${
                        item.status === 'infected' ? 'text-red-600 dark:text-red-400 font-medium' : 'text-red-600 dark:text-red-400'
                      }`}
                    >
                      {uploadStatusLabel(item)}
                    </p>
                  ) : (
                    <>
                      <Progress
                        value={item.status === 'done' ? 100 : item.progress}
                        size="sm"
                        variant={progressBarVariant(item)}
                      />
                      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{uploadStatusLabel(item)}</p>
                    </>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </Modal>
  )
}
