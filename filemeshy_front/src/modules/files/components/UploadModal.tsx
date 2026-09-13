import { CheckCircle2, File as FileIcon, XCircle } from 'lucide-react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'
import { Progress } from '@/ui/progress/Progress'
import { FileUpload } from '@/ui/file-upload/FileUpload'
import { formatBytes } from '@/shared/utils/downloadFile'
import { useFileUpload } from '../hooks/useFileUpload'
import type { FileOut } from '../types'

interface UploadModalProps {
  isOpen: boolean
  onClose: () => void
  folderId: string | undefined
  onUploaded: (file: FileOut) => void
}

export default function UploadModal({ isOpen, onClose, folderId, onUploaded }: UploadModalProps) {
  const { items, isUploading, uploadFiles, resetItems } = useFileUpload(folderId, onUploaded)

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
        <FileUpload multiple onFilesSelected={uploadFiles} />

        {items.length > 0 && (
          <ul className="space-y-3 max-h-64 overflow-y-auto">
            {items.map((item) => (
              <li key={item.id} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                <div className="flex items-center gap-2 mb-2">
                  {item.status === 'done' ? (
                    <CheckCircle2 className="size-4 text-green-500 shrink-0" />
                  ) : item.status === 'error' ? (
                    <XCircle className="size-4 text-red-500 shrink-0" />
                  ) : (
                    <FileIcon className="size-4 text-gray-400 shrink-0" />
                  )}
                  <span className="flex-1 truncate text-sm font-medium text-gray-900 dark:text-white">
                    {item.file.name}
                  </span>
                  <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">
                    {formatBytes(item.file.size)}
                  </span>
                </div>
                {item.status === 'error' ? (
                  <p className="text-xs text-red-600 dark:text-red-400">{item.error}</p>
                ) : (
                  <Progress
                    value={item.progress}
                    size="sm"
                    variant={item.status === 'done' ? 'success' : 'default'}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Modal>
  )
}
