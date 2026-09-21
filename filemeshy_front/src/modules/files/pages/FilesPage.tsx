/**
 * PÁGINA: EXPLORADOR DE ARCHIVOS
 *
 * Hito 1 del "Drive" de FileMeshy: listar, navegar carpetas, subir, crear
 * carpeta, renombrar, mover, papelera con restaurar y búsqueda por nombre.
 * Hito 2: compartir por link (ShareModal) y preview inline de imágenes/PDF
 * (PreviewModal, al doble clic sobre un archivo).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Folder,
  File as FileIcon,
  Upload,
  FolderPlus,
  Trash2,
  Home,
  ChevronRight,
  MoreVertical,
  Download,
  Pencil,
  Move,
  RotateCcw,
  Share2,
  List,
  LayoutGrid,
  Grid2X2,
  UploadCloud,
  Copy,
  Star,
  StarOff,
  ArrowUpNarrowWide,
  ArrowDownWideNarrow,
  Tags,
  History,
} from 'lucide-react'
import { DataTable, type Column } from '@/ui/tables/DataTable'
import { TableFilters } from '@/ui/tables/TableFilters'
import { Dropdown, type DropdownItem } from '@/ui/dropdown/Dropdown'
import { Select } from '@/ui/inputs/Select'
import { Button } from '@/ui/buttons/Button'
import { EmptyState } from '@/ui/empty-states/EmptyState'
import DeleteConfirmDialog from '@/ui/dialogs/DeleteConfirmDialog'
import { toast } from '@/ui/toast/CustomToast'
import { formatBytes } from '@/shared/utils/downloadFile'
import { extractErrorMessage } from '@/shared/utils/errors'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import { Permission } from '@/app/routes'
import { filesService, type FilesSortBy, type FilesSortDir } from '../services/files.service'
import { foldersService } from '../services/folders.service'
import { useFileUpload } from '../hooks/useFileUpload'
import CreateFolderModal from '../components/CreateFolderModal'
import RenameModal, { type RenameTarget } from '../components/RenameModal'
import MoveModal, { type MoveTarget } from '../components/MoveModal'
import UploadModal from '../components/UploadModal'
import ShareModal, { type ShareTarget } from '../components/ShareModal'
import PreviewModal, { type PreviewTarget } from '../components/PreviewModal'
import TagsModal, { type TagsTarget } from '../components/TagsModal'
import FileVersionsModal, { type FileVersionsTarget } from '../components/FileVersionsModal'
import TagChips from '../components/TagChips'
import FileGridView from '../components/FileGridView'
import type { DirectoryListing, FileOut, FolderOut } from '../types'

/** Persistencia del modo de vista, mismo patrón simple que ThemeProvider (ver STORAGE_KEY ahí). */
const VIEW_MODE_STORAGE_KEY = 'filemeshy_files_view_mode'
export type ViewMode = 'list' | 'grid' | 'grid-lg'

const VIEW_MODE_OPTIONS: { value: ViewMode; label: string; icon: typeof List }[] = [
  { value: 'list', label: 'Lista', icon: List },
  { value: 'grid', label: 'Íconos', icon: LayoutGrid },
  { value: 'grid-lg', label: 'Íconos grandes', icon: Grid2X2 },
]

/** Persistencia del orden, mismo patrón simple que VIEW_MODE_STORAGE_KEY arriba. */
const SORT_BY_STORAGE_KEY = 'filemeshy_files_sort_by'
const SORT_DIR_STORAGE_KEY = 'filemeshy_files_sort_dir'

const SORT_BY_OPTIONS: { value: FilesSortBy; label: string }[] = [
  { value: 'name', label: 'Nombre' },
  { value: 'size_bytes', label: 'Tamaño' },
  { value: 'updated_at', label: 'Fecha de modificación' },
  { value: 'created_at', label: 'Fecha de creación' },
]

export interface Row {
  rowId: string
  type: 'folder' | 'file'
  id: string
  name: string
  size: number | null
  updatedAt: string
  raw: FolderOut | FileOut
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('es-ES', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function FilesPage() {
  const { hasPermission } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()

  const folderParam = searchParams.get('folder')
  const currentFolderId: string | null = folderParam || null

  const [listing, setListing] = useState<DirectoryListing | null>(null)
  const [isFirstLoad, setIsFirstLoad] = useState(true)
  const [loading, setLoading] = useState(true)

  const [searchTerm, setSearchTerm] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [showTrash, setShowTrash] = useState(false)

  const [createFolderOpen, setCreateFolderOpen] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [renameTarget, setRenameTarget] = useState<RenameTarget | null>(null)
  const [moveTarget, setMoveTarget] = useState<MoveTarget | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Row | null>(null)
  const [shareTarget, setShareTarget] = useState<ShareTarget | null>(null)
  const [previewTarget, setPreviewTarget] = useState<PreviewTarget | null>(null)
  const [tagsTarget, setTagsTarget] = useState<TagsTarget | null>(null)
  const [versionsTarget, setVersionsTarget] = useState<FileVersionsTarget | null>(null)

  const [viewMode, setViewModeState] = useState<ViewMode>(() => {
    const stored = localStorage.getItem(VIEW_MODE_STORAGE_KEY)
    if (stored === 'list' || stored === 'grid' || stored === 'grid-lg') return stored
    return 'list'
  })
  const setViewMode = (mode: ViewMode) => {
    localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode)
    setViewModeState(mode)
  }

  const [sortBy, setSortByState] = useState<FilesSortBy>(() => {
    const stored = localStorage.getItem(SORT_BY_STORAGE_KEY)
    if (stored === 'name' || stored === 'created_at' || stored === 'updated_at' || stored === 'size_bytes') {
      return stored
    }
    return 'name'
  })
  const setSortBy = (value: FilesSortBy) => {
    localStorage.setItem(SORT_BY_STORAGE_KEY, value)
    setSortByState(value)
  }

  const [sortDir, setSortDirState] = useState<FilesSortDir>(() => {
    const stored = localStorage.getItem(SORT_DIR_STORAGE_KEY)
    return stored === 'asc' || stored === 'desc' ? stored : 'asc'
  })
  const setSortDir = (value: FilesSortDir) => {
    localStorage.setItem(SORT_DIR_STORAGE_KEY, value)
    setSortDirState(value)
  }

  const [favoritesOnly, setFavoritesOnly] = useState(false)

  // Debounce de la búsqueda (300ms) para no pegarle a la API en cada tecla
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchTerm.trim()), 300)
    return () => clearTimeout(timer)
  }, [searchTerm])

  const canModifyHere = !showTrash && !debouncedSearch

  const loadListing = useCallback(async () => {
    setLoading(true)
    try {
      const data = await filesService.list({
        folderId: canModifyHere ? currentFolderId ?? undefined : undefined,
        q: debouncedSearch || undefined,
        trash: showTrash,
        sortBy,
        sortDir,
        favoritesOnly: favoritesOnly || undefined,
      })
      setListing(data)
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al cargar archivos'))
    } finally {
      setLoading(false)
      setIsFirstLoad(false)
    }
  }, [currentFolderId, debouncedSearch, showTrash, canModifyHere, sortBy, sortDir, favoritesOnly])

  useEffect(() => {
    loadListing()
  }, [loadListing])

  const handleNavigate = (folderId: string | null) => {
    setSearchTerm('')
    setShowTrash(false)
    setSearchParams(folderId ? { folder: folderId } : {})
  }

  // Drag&drop de ventana completa: solo si se puede subir acá (no en papelera/búsqueda) y el
  // usuario tiene el permiso -- mismo gate que el botón "Subir" de arriba.
  const canDropFiles = canModifyHere && hasPermission(Permission.UPLOAD_FILES)

  const handleDropUploaded = useCallback(() => {
    loadListing()
  }, [loadListing])

  const { uploadFiles: uploadFilesFromDrop } = useFileUpload(currentFolderId ?? undefined, handleDropUploaded)

  const dragCounterRef = useRef(0)
  const [isDraggingFile, setIsDraggingFile] = useState(false)

  // preventDefault en dragover corre siempre (aun sin permiso de subir) para que el navegador
  // nunca abra el archivo si se suelta fuera de la zona de drop.
  useEffect(() => {
    const handleWindowDragOver = (e: DragEvent) => {
      e.preventDefault()
    }
    window.addEventListener('dragover', handleWindowDragOver)
    return () => window.removeEventListener('dragover', handleWindowDragOver)
  }, [])

  // Contador de profundidad: dragenter/dragleave burbujean por cada hijo del DOM que se
  // atraviesa, así que solo un contador que llegue a 0 evita el parpadeo del overlay.
  //
  // El listener de 'drop' se registra SIEMPRE (aun sin permiso/fuera de una vista que admite
  // modificar contenido) para poder frenar el comportamiento nativo del navegador (abrir o
  // navegar al archivo) con preventDefault -- si solo se registrara cuando canDropFiles es
  // true, en Papelera/búsqueda el dragover seguiría "aceptando" el drag pero sin handler de
  // drop, y el navegador ejecutaría su acción por defecto sacando al usuario de la SPA.
  //
  // uploadOpen (el modal de subida) también apaga el overlay/subida directa: el modal usa
  // createPortal pero sigue siendo parte del DOM real, así que un drop sobre su propia
  // dropzone burbujea igual hasta acá -- sin este gate, el mismo archivo se subiría dos veces
  // (una por la dropzone del modal, otra por este handler global).
  useEffect(() => {
    dragCounterRef.current = 0
    setIsDraggingFile(false)

    const isFileDrag = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes('Files')

    const handleDragEnter = (e: DragEvent) => {
      if (!canDropFiles || uploadOpen) return
      if (!isFileDrag(e)) return
      e.preventDefault()
      dragCounterRef.current += 1
      setIsDraggingFile(true)
    }

    const handleDragLeave = (e: DragEvent) => {
      if (!canDropFiles || uploadOpen) return
      if (!isFileDrag(e)) return
      e.preventDefault()
      dragCounterRef.current = Math.max(0, dragCounterRef.current - 1)
      // Salvaguarda: si el puntero salió del viewport del navegador (coordenadas en el borde
      // o más allá), forzar el cierre del overlay aunque el contador de profundidad no haya
      // llegado a 0 -- evita que quede "pegado" si el drag se suelta fuera de la ventana.
      const leftViewport =
        e.clientX <= 0 || e.clientY <= 0 || e.clientX >= window.innerWidth || e.clientY >= window.innerHeight
      if (dragCounterRef.current === 0 || leftViewport) {
        dragCounterRef.current = 0
        setIsDraggingFile(false)
      }
    }

    const handleDrop = (e: DragEvent) => {
      e.preventDefault()
      dragCounterRef.current = 0
      setIsDraggingFile(false)
      if (!canDropFiles || uploadOpen) return
      const files = e.dataTransfer?.files
      if (files && files.length > 0) {
        uploadFilesFromDrop(Array.from(files))
      }
    }

    window.addEventListener('dragenter', handleDragEnter)
    window.addEventListener('dragleave', handleDragLeave)
    window.addEventListener('drop', handleDrop)
    return () => {
      window.removeEventListener('dragenter', handleDragEnter)
      window.removeEventListener('dragleave', handleDragLeave)
      window.removeEventListener('drop', handleDrop)
    }
  }, [canDropFiles, uploadOpen, uploadFilesFromDrop])

  const rows: Row[] = useMemo(() => {
    if (!listing) return []
    // El orden (nombre/tamaño/fecha, asc/desc) ahora lo aplica el backend vía
    // sort_by/sort_dir (ver loadListing) -- acá solo mapeamos a Row respetando el
    // orden que ya viene en la respuesta, carpetas primero (convención de la UI,
    // independiente del criterio de orden elegido).
    const folderRows: Row[] = listing.folders.map((f) => ({
      rowId: `folder:${f.id}`,
      type: 'folder' as const,
      id: f.id,
      name: f.name,
      size: null,
      updatedAt: f.updated_at,
      raw: f,
    }))
    const fileRows: Row[] = listing.files.map((f) => ({
      rowId: `file:${f.id}`,
      type: 'file' as const,
      id: f.id,
      name: f.name,
      size: f.size_bytes,
      updatedAt: f.updated_at,
      raw: f,
    }))
    return [...folderRows, ...fileRows]
  }, [listing])

  const handleDownload = async (row: Row) => {
    try {
      const url = await filesService.getDownloadUrl(row.id, { forceDownload: true })
      window.location.href = url
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al descargar el archivo'))
    }
  }

  const handlePreview = async (row: Row) => {
    try {
      const url = await filesService.getDownloadUrl(row.id)
      const file = row.raw as FileOut
      setPreviewTarget({ name: row.name, mimeType: file.mime_type, downloadUrl: url, fileId: row.id })
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al abrir la vista previa'))
    }
  }

  const handleRestore = async (row: Row) => {
    try {
      if (row.type === 'folder') {
        await foldersService.restore(row.id)
      } else {
        await filesService.restore(row.id)
      }
      toast.success('Elemento restaurado correctamente')
      await loadListing()
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al restaurar'))
    }
  }

  const handleCopy = async (row: Row) => {
    try {
      if (row.type === 'folder') {
        await foldersService.copy(row.id)
      } else {
        await filesService.copy(row.id)
      }
      toast.success('Copia creada correctamente')
      await loadListing()
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al copiar'))
    }
  }

  const handleToggleFavorite = async (row: Row) => {
    const isFavorite = Boolean(row.raw?.is_favorite)
    try {
      if (row.type === 'folder') {
        await foldersService.setFavorite(row.id, !isFavorite)
      } else {
        await filesService.setFavorite(row.id, !isFavorite)
      }
      toast.success(isFavorite ? 'Quitado de favoritos' : 'Marcado como favorito')
      await loadListing()
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al actualizar favorito'))
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    try {
      if (deleteTarget.type === 'folder') {
        await foldersService.remove(deleteTarget.id)
      } else {
        await filesService.remove(deleteTarget.id)
      }
      toast.success('Elemento movido a la papelera')
      await loadListing()
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al eliminar'))
    } finally {
      setDeleteTarget(null)
    }
  }

  const buildActions = (row: Row): DropdownItem[] => {
    if (showTrash) {
      return [
        {
          label: 'Restaurar',
          icon: <RotateCcw className="size-4" />,
          onClick: () => handleRestore(row),
        },
      ]
    }

    const items: DropdownItem[] = []

    if (row.type === 'file' && hasPermission(Permission.DOWNLOAD_FILES)) {
      items.push({ label: 'Descargar', icon: <Download className="size-4" />, onClick: () => handleDownload(row) })
    }

    if (hasPermission(Permission.CREATE_SHARES)) {
      items.push({
        label: 'Compartir',
        icon: <Share2 className="size-4" />,
        onClick: () => setShareTarget({ id: row.id, name: row.name, type: row.type }),
      })
    }

    const canRename =
      row.type === 'folder' ? hasPermission(Permission.RENAME_FOLDERS) : hasPermission(Permission.RENAME_FILES)
    if (canRename) {
      items.push({
        label: 'Renombrar',
        icon: <Pencil className="size-4" />,
        onClick: () => setRenameTarget({ id: row.id, name: row.name, type: row.type }),
      })
    }

    const canMove =
      row.type === 'folder' ? hasPermission(Permission.MOVE_FOLDERS) : hasPermission(Permission.MOVE_FILES)
    if (canMove) {
      items.push({
        label: 'Mover',
        icon: <Move className="size-4" />,
        onClick: () =>
          setMoveTarget({
            id: row.id,
            name: row.name,
            type: row.type,
            currentFolderId:
              row.type === 'folder' ? (row.raw as FolderOut).parent_id : (row.raw as FileOut).folder_id,
          }),
      })
    }

    // Copiar: mismo permiso para archivo y carpeta -- el backend exige files.upload en ambos
    // casos (POST /files/{id}/copy y POST /folders/{id}/copy), porque copiar consume cuota
    // real igual que subir de nuevo el contenido, no porque se esté creando una carpeta vacía.
    const canCopy = hasPermission(Permission.UPLOAD_FILES)
    if (canCopy) {
      items.push({
        label: 'Copiar',
        icon: <Copy className="size-4" />,
        onClick: () => handleCopy(row),
      })
    }

    // Favorito: no depende de un permiso de escritura sobre el elemento, el backend solo
    // exige el permiso de visualización correspondiente (files.view/folders.view) -- mismo
    // gate que ya se aplica al resto de acciones condicionales de buildActions, para no
    // mostrar la opción a un usuario al que el backend se la va a rechazar con un 403.
    const canFavorite =
      row.type === 'folder' ? hasPermission(Permission.VIEW_FOLDERS) : hasPermission(Permission.VIEW_FILES)
    if (canFavorite) {
      const isFavorite = Boolean(row.raw?.is_favorite)
      items.push({
        label: isFavorite ? 'Quitar de favoritos' : 'Marcar como favorito',
        icon: isFavorite ? <StarOff className="size-4" /> : <Star className="size-4" />,
        onClick: () => handleToggleFavorite(row),
      })
    }

    // Etiquetas: mismo gate que Favorito -- el backend solo exige el permiso de
    // visualización correspondiente (files.view/folders.view), no uno de escritura
    // sobre el elemento en sí.
    const canTag =
      row.type === 'folder' ? hasPermission(Permission.VIEW_FOLDERS) : hasPermission(Permission.VIEW_FILES)
    if (canTag) {
      items.push({
        label: 'Etiquetas',
        icon: <Tags className="size-4" />,
        onClick: () =>
          setTagsTarget({
            id: row.id,
            type: row.type,
            currentTagIds: (row.raw.tags ?? []).map((t) => t.id),
          }),
      })
    }

    // Versiones: solo archivos (las carpetas no tienen versionado) -- mismo gate de
    // permiso de visualización que Favorito/Etiquetas, la validación de ownership la
    // hace el backend.
    if (row.type === 'file' && hasPermission(Permission.VIEW_FILES)) {
      items.push({
        label: 'Ver versiones',
        icon: <History className="size-4" />,
        onClick: () => setVersionsTarget({ id: row.id, name: row.name }),
      })
    }

    const canDelete =
      row.type === 'folder' ? hasPermission(Permission.DELETE_FOLDERS) : hasPermission(Permission.DELETE_FILES)
    if (canDelete) {
      if (items.length > 0) items.push({ divider: true })
      items.push({
        label: 'Eliminar',
        icon: <Trash2 className="size-4" />,
        danger: true,
        onClick: () => setDeleteTarget(row),
      })
    }

    return items
  }

  const columns: Column<Row>[] = [
    {
      key: 'name',
      label: 'Nombre',
      render: (_value, row) => (
        <div className="flex flex-col gap-0.5 py-0.5">
          <div
            className={`flex items-center gap-2 ${
              row.type === 'folder' || !showTrash ? 'cursor-pointer select-none' : ''
            }`}
            onDoubleClick={() => {
              if (row.type === 'folder') handleNavigate(row.id)
              else if (!showTrash) handlePreview(row)
            }}
            title={row.type === 'folder' ? 'Doble clic para entrar' : !showTrash ? 'Doble clic para previsualizar' : undefined}
          >
            {row.type === 'folder' ? (
              <Folder className="size-4 text-brand-500 shrink-0" />
            ) : (
              <FileIcon className="size-4 text-gray-400 shrink-0" />
            )}
            <span className="truncate font-medium text-gray-900 dark:text-white">{row.name}</span>
            {Boolean(row.raw?.is_favorite) && (
              <Star className="size-3.5 shrink-0 fill-current text-yellow-500" aria-label="Favorito" />
            )}
          </div>
          <TagChips tags={row.raw.tags ?? []} className="pl-6" />
        </div>
      ),
    },
    {
      key: 'size',
      label: 'Tamaño',
      width: '120px',
      render: (_value, row) => (row.size === null ? '—' : formatBytes(row.size)),
    },
    {
      key: 'updatedAt',
      label: 'Modificado',
      width: '200px',
      render: (_value, row) => formatDate(row.updatedAt),
    },
    {
      key: 'rowId',
      label: 'Acciones',
      align: 'right',
      width: '80px',
      render: (_value, row) => {
        const items = buildActions(row)
        if (items.length === 0) return null
        return (
          <div className="flex justify-end">
            <Dropdown
              trigger={<MoreVertical className="size-4 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300" />}
              items={items}
            />
          </div>
        )
      },
    },
  ]

  const emptyTitle = showTrash
    ? 'La papelera está vacía'
    : debouncedSearch
      ? 'Sin resultados'
      : 'Esta carpeta está vacía'

  const emptyDescription = showTrash
    ? 'Los archivos y carpetas eliminados aparecen acá. Podés restaurarlos en cualquier momento.'
    : debouncedSearch
      ? `No se encontraron archivos ni carpetas para "${debouncedSearch}".`
      : 'Subí un archivo o creá una carpeta para empezar.'

  return (
    <div className="space-y-6">
      {/* Overlay de drag&drop de ventana completa */}
      {isDraggingFile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-brand-500/10 backdrop-blur-sm pointer-events-none">
          <div className="flex flex-col items-center gap-3 rounded-2xl border-4 border-dashed border-brand-500 bg-white/90 dark:bg-gray-900/90 px-12 py-10 shadow-2xl">
            <UploadCloud className="size-12 text-brand-500" />
            <p className="text-lg font-semibold text-gray-900 dark:text-white">Soltá para subir acá</p>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Archivos</h1>
          <p className="mt-1 text-sm text-muted-foreground">Explorá, subí y organizá tus archivos</p>
        </div>

        <div className="flex gap-2">
          {canModifyHere && hasPermission(Permission.CREATE_FOLDERS) && (
            <Button variant="secondary" leftIcon={<FolderPlus className="size-4" />} onClick={() => setCreateFolderOpen(true)}>
              Nueva carpeta
            </Button>
          )}
          {canModifyHere && hasPermission(Permission.UPLOAD_FILES) && (
            <Button variant="primary" leftIcon={<Upload className="size-4" />} onClick={() => setUploadOpen(true)}>
              Subir
            </Button>
          )}
        </div>
      </div>

      {/* Breadcrumb (solo navegación normal, no en búsqueda ni papelera) */}
      {canModifyHere && (
        <div className="flex flex-wrap items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
          <button
            type="button"
            onClick={() => handleNavigate(null)}
            className={`flex items-center gap-1 rounded-sm px-1.5 py-0.5 hover:bg-gray-100 dark:hover:bg-gray-800 ${
              currentFolderId === null ? 'font-semibold text-brand-600 dark:text-brand-400' : ''
            }`}
          >
            <Home className="size-3.5" />
            Mis archivos
          </button>
          {listing?.breadcrumb.map((crumb, idx) => (
            <span key={crumb.id} className="flex items-center gap-1">
              <ChevronRight className="size-3.5 text-gray-400" />
              <button
                type="button"
                onClick={() => handleNavigate(crumb.id)}
                className={`rounded-sm px-1.5 py-0.5 hover:bg-gray-100 dark:hover:bg-gray-800 ${
                  idx === (listing?.breadcrumb.length ?? 0) - 1
                    ? 'font-semibold text-brand-600 dark:text-brand-400'
                    : ''
                }`}
              >
                {crumb.name}
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Filtros: búsqueda + toggle de papelera */}
      <TableFilters
        enableSearch
        searchValue={searchTerm}
        onSearchChange={setSearchTerm}
        searchPlaceholder="Buscar archivos y carpetas por nombre..."
        extraFilters={
          <div className="flex items-center gap-2 flex-wrap">
            {/* Orden: campo + dirección. Se persiste igual que el modo de vista. */}
            <Select
              options={SORT_BY_OPTIONS}
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as FilesSortBy)}
              placeholder=""
              fullWidth={false}
              className="py-1.5!"
              aria-label="Ordenar por"
            />
            <button
              type="button"
              onClick={() => setSortDir(sortDir === 'asc' ? 'desc' : 'asc')}
              title={sortDir === 'asc' ? 'Orden ascendente' : 'Orden descendente'}
              aria-label={sortDir === 'asc' ? 'Orden ascendente' : 'Orden descendente'}
              className="inline-flex items-center justify-center rounded-md p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-gray-800 transition-colors"
            >
              {sortDir === 'asc' ? (
                <ArrowUpNarrowWide className="size-4" />
              ) : (
                <ArrowDownWideNarrow className="size-4" />
              )}
            </button>

            <div className="inline-flex items-center rounded-lg bg-gray-100 dark:bg-gray-800 p-0.5">
              {VIEW_MODE_OPTIONS.map(({ value, label, icon: Icon }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setViewMode(value)}
                  title={label}
                  aria-label={label}
                  aria-pressed={viewMode === value}
                  className={`inline-flex items-center justify-center rounded-md p-1.5 transition-colors ${
                    viewMode === value
                      ? 'bg-white text-brand-600 shadow-sm dark:bg-gray-700 dark:text-brand-400'
                      : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                  }`}
                >
                  <Icon className="size-4" />
                </button>
              ))}
            </div>

            {!showTrash && (
              <Button
                variant={favoritesOnly ? 'primary' : 'secondary'}
                leftIcon={<Star className="size-4" />}
                onClick={() => setFavoritesOnly((v) => !v)}
              >
                Favoritos
              </Button>
            )}

            <Button
              variant={showTrash ? 'primary' : 'secondary'}
              leftIcon={<Trash2 className="size-4" />}
              onClick={() => {
                setShowTrash((v) => !v)
                setSearchTerm('')
                setFavoritesOnly(false)
              }}
            >
              {showTrash ? 'Volver a Archivos' : 'Papelera'}
            </Button>
          </div>
        }
      />

      {/* Tabla */}
      {isFirstLoad ? (
        <div className="bg-card rounded-lg border border-border p-12">
          <div className="flex flex-col items-center justify-center">
            <div className="w-12 h-12 border-4 border-brand-500 border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-muted-foreground">Cargando archivos...</p>
          </div>
        </div>
      ) : rows.length === 0 && !loading ? (
        <div
          className="flex items-center justify-center bg-linear-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800 border border-border rounded-xl shadow-xs"
          style={{ minHeight: '450px' }}
        >
          <EmptyState
            icon={<Folder className="size-20 text-muted-foreground" strokeWidth={1.5} />}
            title={emptyTitle}
            description={emptyDescription}
            primaryAction={
              canModifyHere && hasPermission(Permission.UPLOAD_FILES)
                ? { label: 'Subir archivo', onClick: () => setUploadOpen(true) }
                : undefined
            }
          />
        </div>
      ) : (
        <div className={loading ? 'opacity-70 transition-opacity' : ''}>
          {viewMode === 'list' ? (
            <DataTable columns={columns} data={rows} rowKey="rowId" loading={loading} emptyMessage="Sin elementos" />
          ) : (
            <FileGridView
              rows={rows}
              size={viewMode === 'grid-lg' ? 'lg' : 'md'}
              showTrash={showTrash}
              onNavigate={handleNavigate}
              onPreview={handlePreview}
              buildActions={buildActions}
            />
          )}
        </div>
      )}

      {/* Modales */}
      <CreateFolderModal
        isOpen={createFolderOpen}
        onClose={() => setCreateFolderOpen(false)}
        parentId={currentFolderId}
        onCreated={() => loadListing()}
      />

      <UploadModal
        isOpen={uploadOpen}
        onClose={() => setUploadOpen(false)}
        folderId={currentFolderId ?? undefined}
        onUploaded={() => loadListing()}
      />

      <RenameModal target={renameTarget} onClose={() => setRenameTarget(null)} onRenamed={() => loadListing()} />

      <MoveModal target={moveTarget} onClose={() => setMoveTarget(null)} onMoved={() => loadListing()} />

      <ShareModal target={shareTarget} onClose={() => setShareTarget(null)} />

      <PreviewModal target={previewTarget} onClose={() => setPreviewTarget(null)} />

      <TagsModal target={tagsTarget} onClose={() => setTagsTarget(null)} onSaved={() => loadListing()} />

      <FileVersionsModal
        target={versionsTarget}
        onClose={() => setVersionsTarget(null)}
        onSaved={() => loadListing()}
      />

      {deleteTarget && (
        <DeleteConfirmDialog
          isOpen={true}
          onClose={() => setDeleteTarget(null)}
          onConfirm={confirmDelete}
          title={deleteTarget.type === 'folder' ? 'Eliminar carpeta' : 'Eliminar archivo'}
          description={`¿Estás seguro de mover "${deleteTarget.name}" a la papelera?`}
        />
      )}
    </div>
  )
}
