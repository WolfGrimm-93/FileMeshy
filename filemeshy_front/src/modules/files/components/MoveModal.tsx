import { useEffect, useState, useCallback } from 'react'
import { Folder, ChevronRight, Home, MoveRight } from 'lucide-react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'
import { toast } from '@/ui/toast/CustomToast'
import { extractErrorMessage } from '@/shared/utils/errors'
import { foldersService } from '../services/folders.service'
import { filesService } from '../services/files.service'
import type { BreadcrumbItem, FolderOut } from '../types'

export interface MoveTarget {
  id: string
  name: string
  type: 'folder' | 'file'
  /** Carpeta actual del item (para no ofrecerla como destino trivial). */
  currentFolderId: string | null
}

interface MoveModalProps {
  target: MoveTarget | null
  onClose: () => void
  onMoved: (target: MoveTarget, newFolderId: string | null) => void
}

export default function MoveModal({ target, onClose, onMoved }: MoveModalProps) {
  const [browseFolderId, setBrowseFolderId] = useState<string | null>(null)
  const [breadcrumb, setBreadcrumb] = useState<BreadcrumbItem[]>([])
  const [folders, setFolders] = useState<FolderOut[]>([])
  const [loading, setLoading] = useState(false)
  const [moving, setMoving] = useState(false)

  // Reiniciar el navegador de carpetas cada vez que se abre para un item nuevo
  useEffect(() => {
    if (target) {
      setBrowseFolderId(null)
      setBreadcrumb([])
    }
  }, [target])

  const loadFolders = useCallback(async (folderId: string | null) => {
    setLoading(true)
    try {
      const listing = await filesService.list({ folderId: folderId ?? undefined })
      // No ofrecer como destino la propia carpeta que se está moviendo (no se
      // puede mover una carpeta dentro de sí misma) -- el resto de ciclos
      // (mover dentro de un descendiente) los valida el backend.
      setFolders(listing.folders.filter((f) => f.id !== target?.id))
      setBreadcrumb(listing.breadcrumb)
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al listar carpetas'))
    } finally {
      setLoading(false)
    }
  }, [target])

  useEffect(() => {
    if (!target) return
    loadFolders(browseFolderId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, browseFolderId])

  const handleClose = () => {
    if (moving) return
    onClose()
  }

  const handleConfirm = async () => {
    if (!target) return

    if (browseFolderId === target.currentFolderId) {
      toast.error('El elemento ya está en esa carpeta')
      return
    }

    setMoving(true)
    try {
      if (target.type === 'folder') {
        await foldersService.move(target.id, browseFolderId)
      } else {
        await filesService.move(target.id, browseFolderId)
      }
      toast.success('Elemento movido correctamente')
      onMoved(target, browseFolderId)
      onClose()
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al mover el elemento'))
    } finally {
      setMoving(false)
    }
  }

  return (
    <Modal
      isOpen={!!target}
      onClose={handleClose}
      title={target ? `Mover "${target.name}"` : 'Mover'}
      size="md"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={handleClose} disabled={moving}>
            Cancelar
          </Button>
          <Button
            variant="primary"
            leftIcon={<MoveRight className="size-4" />}
            onClick={handleConfirm}
            isLoading={moving}
            loadingText="Moviendo..."
          >
            Mover aquí
          </Button>
        </div>
      }
    >
      <div className="space-y-3">
        {/* Breadcrumb del navegador de destino */}
        <div className="flex flex-wrap items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
          <button
            type="button"
            onClick={() => setBrowseFolderId(null)}
            className={`flex items-center gap-1 rounded-sm px-1.5 py-0.5 hover:bg-gray-100 dark:hover:bg-gray-800 ${
              browseFolderId === null ? 'font-semibold text-brand-600 dark:text-brand-400' : ''
            }`}
          >
            <Home className="size-3.5" />
            Raíz
          </button>
          {breadcrumb.map((crumb) => (
            <span key={crumb.id} className="flex items-center gap-1">
              <ChevronRight className="size-3.5 text-gray-400" />
              <button
                type="button"
                onClick={() => setBrowseFolderId(crumb.id)}
                className={`rounded-sm px-1.5 py-0.5 hover:bg-gray-100 dark:hover:bg-gray-800 ${
                  browseFolderId === crumb.id ? 'font-semibold text-brand-600 dark:text-brand-400' : ''
                }`}
              >
                {crumb.name}
              </button>
            </span>
          ))}
        </div>

        {/* Lista de subcarpetas navegables */}
        <div className="max-h-72 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="size-6 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : folders.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
              No hay subcarpetas acá
            </p>
          ) : (
            <ul className="divide-y divide-gray-100 dark:divide-gray-800">
              {folders.map((folder) => (
                <li key={folder.id}>
                  <button
                    type="button"
                    onDoubleClick={() => setBrowseFolderId(folder.id)}
                    onClick={() => setBrowseFolderId(folder.id)}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 hover:bg-brand-50 dark:text-gray-300 dark:hover:bg-brand-900/10"
                    title="Doble clic para entrar"
                  >
                    <Folder className="size-4 text-brand-500 shrink-0" />
                    <span className="truncate">{folder.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <p className="text-xs text-gray-500 dark:text-gray-400">
          Navegá con doble clic en una carpeta y confirmá con "Mover aquí" para elegirla como destino.
        </p>
      </div>
    </Modal>
  )
}
