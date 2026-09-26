/**
 * PÁGINA: "Compartido conmigo" (Ronda 3)
 *
 * Lista los shares dirigidos al usuario actual (`GET /shares/with-me`,
 * `shared_with_email` == email del usuario logueado en el back). A diferencia
 * de los links públicos del Hito 2, estos NO tienen token de link: se accede
 * autenticado vía `GET /shares/{id}` / `.../download/{file_id}`.
 *
 * Si el share es de carpeta, "Ver" abre un mini-explorador de solo lectura
 * (mismo patrón que PublicSharePage pero autenticado). Si el permiso es
 * 'edit', además se puede subir un archivo nuevo a la carpeta o reemplazar el
 * contenido de un archivo, según corresponda.
 */
import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import {
  ChevronRight,
  Download,
  File as FileIcon,
  Folder,
  Home,
  RefreshCw,
  Share2,
  Upload,
} from 'lucide-react'
import { DataTable, type Column } from '@/ui/tables/DataTable'
import { Button } from '@/ui/buttons/Button'
import { Badge } from '@/ui/badges/Badge'
import { Modal } from '@/ui/modals/Modal'
import { EmptyState } from '@/ui/empty-states/EmptyState'
import { toast } from '@/ui/toast/CustomToast'
import { formatBytes } from '@/shared/utils/downloadFile'
import { extractErrorMessage } from '@/shared/utils/errors'
import { parseDate } from '@/shared/utils/dates'
import { sharesService } from '../services/shares.service'
import type { FileOut, FolderOut, PublicShareResponse, SharedWithMeItem, SharePermission } from '../types'

// Parseo tolerante (shared/utils/dates): acepta "+00:00Z" y nunca devuelve "Invalid Date"
function formatDate(iso: string): string {
  const date = parseDate(iso)
  if (!date) return '—'
  return date.toLocaleString('es-ES', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function permissionBadge(permission: SharePermission) {
  return permission === 'edit' ? <Badge variant="info">Editor</Badge> : <Badge variant="gray">Lector</Badge>
}

/**
 * Mini-explorador de solo lectura para una carpeta compartida -- mismo patrón
 * que la rama "folder" de PublicSharePage, pero autenticado (sin token en la
 * URL) y dentro de un Modal en vez de una página completa.
 */
interface SharedFolderTarget {
  shareId: string
  name: string
}

interface SharedFolderModalProps {
  target: SharedFolderTarget | null
  onClose: () => void
}

/**
 * Mount-gate: no monta nada sin target, y el interior se remonta por shareId,
 * así cada apertura arranca en la raíz sin efectos que reseteen estado.
 */
function SharedFolderModal({ target, onClose }: SharedFolderModalProps) {
  if (!target) return null
  return <SharedFolderModalInner key={target.shareId} target={target} onClose={onClose} />
}

function SharedFolderModalInner({ target, onClose }: { target: SharedFolderTarget; onClose: () => void }) {
  const [path, setPath] = useState<string | null>(null)
  // Resultado atado a la ruta que lo produjo: `loading` se deriva de que la ruta actual
  // todavía no tenga resultado.
  const [result, setResult] = useState<{ key: string; data: PublicShareResponse | null } | null>(null)
  const pathKey = path ?? ''
  const loading = result?.key !== pathKey
  const data = result?.data ?? null

  useEffect(() => {
    let cancelled = false
    sharesService
      .getShared(target.shareId, path ?? undefined)
      .then((response) => {
        if (!cancelled) setResult({ key: pathKey, data: response })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        toast.error(extractErrorMessage(error, 'Error al cargar el contenido de la carpeta'))
        setResult((prev) => ({ key: pathKey, data: prev?.data ?? null }))
      })
    return () => {
      cancelled = true
    }
  }, [target.shareId, path, pathKey])

  const handleFileOpen = async (file: FileOut) => {
    try {
      const url = await sharesService.getSharedDownloadUrl(target.shareId, file.id)
      window.location.assign(url)
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al descargar el archivo'))
    }
  }

  return (
    <Modal isOpen onClose={onClose} title={target.name} size="lg">
      <div className="flex items-center gap-2 border-b border-gray-200 pb-3 text-sm text-gray-600 dark:border-gray-700 dark:text-gray-400">
        <button
          type="button"
          onClick={() => setPath(null)}
          className={`flex items-center gap-1 rounded-sm px-1.5 py-0.5 hover:bg-gray-100 dark:hover:bg-gray-800 ${
            !path ? 'font-semibold text-brand-600 dark:text-brand-400' : ''
          }`}
        >
          <Home className="size-3.5" />
          {target.name}
        </button>
        {path && (
          <span className="flex items-center gap-1">
            <ChevronRight className="size-3.5 text-gray-400" />
            <span className="font-semibold text-brand-600 dark:text-brand-400">Subcarpeta</span>
          </span>
        )}
      </div>

      {loading ? (
        <p className="py-6 text-center text-sm text-gray-500 dark:text-gray-400">Cargando...</p>
      ) : !data || data.type !== 'folder' ? (
        <p className="py-6 text-center text-sm text-gray-500 dark:text-gray-400">
          No se pudo cargar el contenido.
        </p>
      ) : data.folders.length === 0 && data.files.length === 0 ? (
        <p className="py-6 text-center text-sm text-gray-500 dark:text-gray-400">Esta carpeta está vacía.</p>
      ) : (
        <ul className="max-h-96 divide-y divide-gray-200 overflow-y-auto dark:divide-gray-700">
          {[...data.folders]
            .sort((a: FolderOut, b: FolderOut) => a.name.localeCompare(b.name))
            .map((folder) => (
              <li
                key={folder.id}
                className="flex cursor-pointer select-none items-center gap-3 px-2 py-3 hover:bg-gray-50 dark:hover:bg-gray-900"
                onDoubleClick={() => setPath(folder.id)}
                title="Doble clic para entrar"
              >
                <Folder className="size-5 shrink-0 text-brand-500" />
                <span className="truncate text-sm font-medium text-gray-900 dark:text-white">{folder.name}</span>
              </li>
            ))}
          {[...data.files]
            .sort((a: FileOut, b: FileOut) => a.name.localeCompare(b.name))
            .map((file) => (
              <li
                key={file.id}
                className="flex cursor-pointer select-none items-center gap-3 px-2 py-3 hover:bg-gray-50 dark:hover:bg-gray-900"
                onDoubleClick={() => handleFileOpen(file)}
                title="Doble clic para descargar"
              >
                <FileIcon className="size-5 shrink-0 text-gray-400" />
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-gray-900 dark:text-white">
                  {file.name}
                </span>
                <span className="shrink-0 text-xs text-gray-500 dark:text-gray-400">{formatBytes(file.size_bytes)}</span>
              </li>
            ))}
        </ul>
      )}
    </Modal>
  )
}

export default function SharedWithMePage() {
  const [items, setItems] = useState<SharedWithMeItem[]>([])
  const [isFirstLoad, setIsFirstLoad] = useState(true)
  const [loading, setLoading] = useState(true)
  const [busyShareId, setBusyShareId] = useState<string | null>(null)
  const [folderTarget, setFolderTarget] = useState<SharedFolderTarget | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const pendingActionRef = useRef<{ shareId: string; kind: 'upload' | 'replace' } | null>(null)

  // `loading` ya arranca en true y esta carga solo ocurre al montar: no hace falta setLoading(true)
  useEffect(() => {
    let cancelled = false
    sharesService
      .listSharedWithMe()
      .then((data) => {
        if (!cancelled) setItems(data)
      })
      .catch((error: unknown) => {
        if (!cancelled) toast.error(extractErrorMessage(error, 'Error al cargar lo compartido con vos'))
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
          setIsFirstLoad(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const handleOpen = async (item: SharedWithMeItem) => {
    if (item.resource_type === 'folder') {
      setFolderTarget({ shareId: item.share_id, name: item.resource_name })
      return
    }
    try {
      const response = await sharesService.getShared(item.share_id)
      if (response.type === 'file') {
        window.location.assign(response.download_url)
      }
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al descargar el archivo'))
    }
  }

  const triggerFileInput = (shareId: string, kind: 'upload' | 'replace') => {
    pendingActionRef.current = { shareId, kind }
    fileInputRef.current?.click()
  }

  const handleFileInputChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    const pending = pendingActionRef.current
    pendingActionRef.current = null
    // Reset del input para poder volver a elegir el mismo archivo más adelante.
    e.target.value = ''
    if (!file || !pending) return

    setBusyShareId(pending.shareId)
    try {
      if (pending.kind === 'upload') {
        await sharesService.uploadToSharedFolder(pending.shareId, file)
        toast.success('Archivo subido correctamente')
      } else {
        await sharesService.replaceSharedFileContent(pending.shareId, file)
        toast.success('Contenido reemplazado correctamente')
      }
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al procesar el archivo'))
    } finally {
      setBusyShareId(null)
    }
  }

  const columns: Column<SharedWithMeItem>[] = [
    {
      key: 'resource_name',
      label: 'Nombre',
      render: (_value, item) => (
        <div className="flex items-center gap-2">
          {item.resource_type === 'folder' ? (
            <Folder className="size-4 shrink-0 text-brand-500" />
          ) : (
            <FileIcon className="size-4 shrink-0 text-gray-400" />
          )}
          <span className="truncate font-medium text-gray-900 dark:text-white">{item.resource_name}</span>
        </div>
      ),
    },
    {
      key: 'shared_by_email',
      label: 'Compartido por',
      render: (_value, item) => (
        <span className="text-sm text-gray-700 dark:text-gray-300">{item.shared_by_email}</span>
      ),
    },
    {
      key: 'resource_type',
      label: 'Tipo',
      width: '110px',
      render: (_value, item) => (item.resource_type === 'folder' ? 'Carpeta' : 'Archivo'),
    },
    {
      key: 'permission',
      label: 'Permiso',
      width: '110px',
      render: (_value, item) => permissionBadge(item.permission),
    },
    {
      key: 'expires_at',
      label: 'Expira',
      width: '180px',
      render: (_value, item) => (item.expires_at ? formatDate(item.expires_at) : 'No expira'),
    },
    {
      key: 'share_id',
      label: 'Acciones',
      align: 'right',
      width: '260px',
      render: (_value, item) => {
        const isBusy = busyShareId === item.share_id
        return (
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              leftIcon={item.resource_type === 'folder' ? <Folder className="size-3.5" /> : <Download className="size-3.5" />}
              onClick={() => handleOpen(item)}
            >
              {item.resource_type === 'folder' ? 'Ver' : 'Descargar'}
            </Button>

            {item.permission === 'edit' && item.resource_type === 'folder' && (
              <Button
                variant="ghost"
                size="sm"
                leftIcon={<Upload className="size-3.5" />}
                isLoading={isBusy}
                onClick={() => triggerFileInput(item.share_id, 'upload')}
              >
                Subir archivo
              </Button>
            )}

            {item.permission === 'edit' && item.resource_type === 'file' && (
              <Button
                variant="ghost"
                size="sm"
                leftIcon={<RefreshCw className="size-3.5" />}
                isLoading={isBusy}
                onClick={() => triggerFileInput(item.share_id, 'replace')}
              >
                Reemplazar contenido
              </Button>
            )}
          </div>
        )
      },
    },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-foreground">Compartido conmigo</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Archivos y carpetas que otras personas compartieron con vos directamente
        </p>
      </div>

      {isFirstLoad ? (
        <div className="bg-card rounded-lg border border-border p-12">
          <div className="flex flex-col items-center justify-center">
            <div className="w-12 h-12 border-4 border-brand-500 border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-muted-foreground">Cargando...</p>
          </div>
        </div>
      ) : items.length === 0 && !loading ? (
        <div
          className="flex items-center justify-center bg-linear-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800 border border-border rounded-xl shadow-xs"
          style={{ minHeight: '450px' }}
        >
          <EmptyState
            icon={<Share2 className="size-20 text-muted-foreground" strokeWidth={1.5} />}
            title="Todavía no compartieron nada con vos"
            description="Cuando alguien comparta un archivo o carpeta directamente con tu email, va a aparecer acá."
          />
        </div>
      ) : (
        <div className={loading ? 'opacity-70 transition-opacity' : ''}>
          <DataTable columns={columns} data={items} rowKey="share_id" loading={loading} emptyMessage="Sin elementos" />
        </div>
      )}

      <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileInputChange} />

      <SharedFolderModal target={folderTarget} onClose={() => setFolderTarget(null)} />
    </div>
  )
}
