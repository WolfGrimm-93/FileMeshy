import { useCallback, useEffect, useRef, useState } from 'react'
import { History, RotateCcw, Upload } from 'lucide-react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'
import { Progress } from '@/ui/progress/Progress'
import { toast } from '@/ui/toast/CustomToast'
import { formatBytes } from '@/shared/utils/downloadFile'
import { formatDateTime } from '@/shared/utils/dates'
import { extractErrorMessage } from '@/shared/utils/errors'
import { filesService } from '../services/files.service'
import type { FileVersionOut } from '../types'

export interface FileVersionsTarget {
  id: string
  name: string
}

interface FileVersionsModalProps {
  target: FileVersionsTarget | null
  onClose: () => void
  /** Se dispara al subir una versión nueva o restaurar una anterior -- el archivo pudo
   * haber cambiado de tamaño/fecha y `FilesPage` necesita recargar su listado principal. */
  onSaved: () => void
}

export default function FileVersionsModal({ target, onClose, onSaved }: FileVersionsModalProps) {
  const [versions, setVersions] = useState<FileVersionOut[]>([])
  const [loading, setLoading] = useState(false)
  const [restoringId, setRestoringId] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadVersions = useCallback(async () => {
    if (!target) return
    setLoading(true)
    try {
      const data = await filesService.listVersions(target.id)
      setVersions(data)
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al cargar el historial de versiones'))
    } finally {
      setLoading(false)
    }
  }, [target])

  // Al abrir (cambio de target): recargar el historial completo -- mismo patrón
  // target-driven que TagsModal.
  useEffect(() => {
    if (!target) return
    setVersions([])
    loadVersions()
  }, [target, loadVersions])

  const handleClose = () => {
    if (uploading || restoringId) return
    onClose()
  }

  const handleUploadClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !target) return

    setUploading(true)
    setUploadProgress(0)
    try {
      await filesService.uploadNewVersion(target.id, file, setUploadProgress)
      toast.success('Nueva versión subida correctamente')
      await loadVersions()
      onSaved()
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al subir la nueva versión'))
    } finally {
      setUploading(false)
      setUploadProgress(0)
    }
  }

  const handleRestore = async (version: FileVersionOut) => {
    if (!target) return
    setRestoringId(version.id)
    try {
      await filesService.restoreVersion(target.id, version.id)
      toast.success(`Versión ${version.version_number} restaurada correctamente`)
      // Recargar el historial del propio modal -- la versión restaurada pasa a
      // ser la primera (actual) y deja de tener botón de "Restaurar".
      await loadVersions()
      onSaved()
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al restaurar la versión'))
    } finally {
      setRestoringId(null)
    }
  }

  return (
    <Modal
      isOpen={!!target}
      onClose={handleClose}
      title={target ? `Versiones de "${target.name}"` : 'Versiones'}
      size="lg"
      closeOnOverlayClick={!uploading && !restoringId}
      showCloseButton={!uploading && !restoringId}
      footer={
        <div className="flex justify-end">
          <Button variant="ghost" onClick={handleClose} disabled={uploading || Boolean(restoringId)}>
            Cerrar
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <div>
          <Button
            variant="secondary"
            leftIcon={<Upload className="size-4" />}
            onClick={handleUploadClick}
            isLoading={uploading}
            loadingText="Subiendo..."
            disabled={uploading}
          >
            Subir nueva versión
          </Button>
          <input ref={fileInputRef} type="file" onChange={handleFileSelected} className="hidden" />

          {uploading && (
            <Progress value={uploadProgress} showLabel className="mt-3" />
          )}
        </div>

        <div className="border-t border-gray-200 pt-4 dark:border-gray-700">
          {loading ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">Cargando historial de versiones...</p>
          ) : versions.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Este archivo todavía no tiene versiones registradas.
            </p>
          ) : (
            <ul className="space-y-2">
              {versions.map((version, index) => {
                const isCurrent = index === 0
                return (
                  <li
                    key={version.id}
                    className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 p-3 dark:border-gray-700"
                  >
                    <div className="flex min-w-0 items-start gap-2">
                      <History className="mt-0.5 size-4 shrink-0 text-gray-400" />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-gray-900 dark:text-white">
                            Versión {version.version_number}
                          </span>
                          {isCurrent && (
                            <span className="inline-flex items-center rounded-full bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-700 dark:bg-brand-950 dark:text-brand-400">
                              Actual
                            </span>
                          )}
                        </div>
                        <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                          {formatBytes(version.size_bytes)} · {formatDateTime(version.created_at) ?? '—'} ·{' '}
                          {version.created_by_email ?? 'Usuario desconocido'}
                        </p>
                      </div>
                    </div>

                    {!isCurrent && (
                      <Button
                        variant="ghost"
                        size="sm"
                        leftIcon={<RotateCcw className="size-4" />}
                        onClick={() => handleRestore(version)}
                        isLoading={restoringId === version.id}
                        loadingText="Restaurando..."
                        disabled={Boolean(restoringId) || uploading}
                      >
                        Restaurar
                      </Button>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>
    </Modal>
  )
}
