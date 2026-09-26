import { useEffect, useState } from 'react'
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
  /** 'move' (default) mueve el elemento; 'copy' lo copia a la carpeta elegida (raíz = null explícito). */
  mode?: 'move' | 'copy'
  target: MoveTarget | null
  onClose: () => void
  onMoved: (target: MoveTarget, newFolderId: string | null) => void
}

/**
 * Mount-gate: sin target no monta nada, y el interior se remonta por `target.id`,
 * así cada apertura arranca en la raíz sin efectos que reseteen el navegador.
 */
export default function MoveModal({ mode = 'move', target, onClose, onMoved }: MoveModalProps) {
  if (!target) return null
  return <MoveModalInner key={target.id} mode={mode} target={target} onClose={onClose} onMoved={onMoved} />
}

interface MoveModalInnerProps {
  mode: 'move' | 'copy'
  target: MoveTarget
  onClose: () => void
  onMoved: (target: MoveTarget, newFolderId: string | null) => void
}

function MoveModalInner({ mode, target, onClose, onMoved }: MoveModalInnerProps) {
  const isCopy = mode === 'copy'
  // Copiar arranca en la carpeta actual del elemento (destino natural); mover, en la raíz
  const [browseFolderId, setBrowseFolderId] = useState<string | null>(isCopy ? target.currentFolderId : null)
  // Resultado atado a la carpeta que se estaba navegando: `loading` se deriva de que la
  // carpeta actual todavía no tenga resultado (sin setState síncrono en efectos).
  const [result, setResult] = useState<{
    key: string
    folders: FolderOut[]
    breadcrumb: BreadcrumbItem[]
    failed: boolean
  } | null>(null)
  const [moving, setMoving] = useState(false)
  // Contador para reintentar tras un error de listado (entra en la clave de la petición)
  const [retryTick, setRetryTick] = useState(0)

  const browseKey = `${browseFolderId ?? ''}|${retryTick}`
  const loading = result?.key !== browseKey
  const folders = result?.folders ?? []
  const breadcrumb = result?.breadcrumb ?? []
  // Solo hay error si el resultado guardado es el de la petición actual
  const loadFailed = !loading && (result?.failed ?? false)

  useEffect(() => {
    let cancelled = false
    filesService
      .list({ folderId: browseFolderId ?? undefined })
      .then((listing) => {
        if (cancelled) return
        // No ofrecer como destino la propia carpeta que se está moviendo (no se
        // puede mover una carpeta dentro de sí misma) -- el resto de ciclos
        // (mover dentro de un descendiente) los valida el backend.
        setResult({
          key: browseKey,
          folders: listing.folders.filter((f) => f.id !== target.id),
          breadcrumb: listing.breadcrumb,
          failed: false,
        })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        toast.error(extractErrorMessage(error, 'Error al listar carpetas'))
        // Nunca se conserva la lista del destino anterior bajo la clave nueva: se muestra el
        // error (con reintento) y se bloquea confirmar hasta tener el listado real del destino.
        setResult({ key: browseKey, folders: [], breadcrumb: [], failed: true })
      })
    return () => {
      cancelled = true
    }
  }, [target.id, browseFolderId, browseKey])

  const handleClose = () => {
    if (moving) return
    onClose()
  }

  const handleConfirm = async () => {
    if (!isCopy && browseFolderId === target.currentFolderId) {
      toast.error('El elemento ya está en esa carpeta')
      return
    }

    setMoving(true)
    try {
      if (isCopy) {
        // Destino explícito y sin ambigüedad: id de carpeta o null (raíz)
        if (target.type === 'folder') {
          await foldersService.copy(target.id, browseFolderId)
        } else {
          await filesService.copy(target.id, browseFolderId)
        }
      } else if (target.type === 'folder') {
        await foldersService.move(target.id, browseFolderId)
      } else {
        await filesService.move(target.id, browseFolderId)
      }
      toast.success(isCopy ? 'Copia creada correctamente' : 'Elemento movido correctamente')
      onMoved(target, browseFolderId)
      onClose()
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, isCopy ? 'Error al copiar el elemento' : 'Error al mover el elemento'))
    } finally {
      setMoving(false)
    }
  }

  return (
    <Modal
      isOpen
      onClose={handleClose}
      title={`${isCopy ? 'Copiar' : 'Mover'} "${target.name}"`}
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
            disabled={loadFailed}
            loadingText={isCopy ? 'Copiando...' : 'Moviendo...'}
          >
            {isCopy ? 'Copiar aquí' : 'Mover aquí'}
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
          ) : loadFailed ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <p className="text-sm text-red-600 dark:text-red-500">No se pudo cargar esta carpeta.</p>
              <Button variant="secondary" size="sm" onClick={() => setRetryTick((t) => t + 1)}>
                Reintentar
              </Button>
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
          Navegá con doble clic en una carpeta y confirmá con "{isCopy ? 'Copiar aquí' : 'Mover aquí'}" para elegirla como destino.
        </p>
      </div>
    </Modal>
  )
}
