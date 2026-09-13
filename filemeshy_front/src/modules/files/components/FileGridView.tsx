/**
 * Vista de íconos (grilla) del explorador de archivos -- alternativa a la
 * tabla (DataTable) para los modos "Íconos" e "Íconos grandes" del selector
 * de FilesPage. Reusa el mismo `rows`/`buildActions`/navegación/preview que
 * ya arma la página: acá solo cambia el layout de renderizado, no la lógica.
 *
 * MVP con íconos genéricos por tipo de archivo (mapper de fileTypeIcon.ts),
 * sin preview real de imagen/PDF -- evita cargar archivos completos al
 * listar carpetas grandes (decisión de producto ya definida).
 */
import { Folder, MoreVertical } from 'lucide-react'
import { Dropdown, type DropdownItem } from '@/ui/dropdown/Dropdown'
import { getFileTypeIcon } from '@/shared/utils/fileTypeIcon'
import type { Row } from '../pages/FilesPage'
import type { FileOut } from '../types'

interface FileGridViewProps {
  rows: Row[]
  size: 'md' | 'lg'
  showTrash: boolean
  onNavigate: (folderId: string | null) => void
  onPreview: (row: Row) => void
  buildActions: (row: Row) => DropdownItem[]
}

const GRID_CLASSES: Record<'md' | 'lg', string> = {
  md: 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8',
  lg: 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5',
}

const ICON_SIZE_CLASSES: Record<'md' | 'lg', string> = {
  md: 'size-10',
  lg: 'size-16',
}

export default function FileGridView({ rows, size, showTrash, onNavigate, onPreview, buildActions }: FileGridViewProps) {
  // Mismo mensaje que emptyMessage de la vista Lista (DataTable), para consistencia entre
  // los 3 modos -- sin esto la grilla queda en blanco (ej. mientras loading===true recién
  // entrando a una carpeta, FilesPage todavía no reemplaza este componente por EmptyState).
  if (rows.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-sm text-gray-500 dark:text-gray-400">
        Sin elementos
      </div>
    )
  }

  return (
    <div className={`grid gap-3 ${GRID_CLASSES[size]}`}>
      {rows.map((row) => {
        const items = buildActions(row)
        const Icon = row.type === 'folder' ? Folder : getFileTypeIcon((row.raw as FileOut).mime_type)
        const iconColorClass = row.type === 'folder' ? 'text-brand-500' : 'text-gray-400'

        return (
          <div
            key={row.rowId}
            className="group relative flex flex-col items-center gap-2 rounded-lg border border-transparent p-3 text-center hover:border-border hover:bg-gray-50 dark:hover:bg-gray-800/60 cursor-pointer select-none"
            onDoubleClick={() => {
              if (row.type === 'folder') onNavigate(row.id)
              else if (!showTrash) onPreview(row)
            }}
            title={
              row.type === 'folder' ? 'Doble clic para entrar' : !showTrash ? 'Doble clic para previsualizar' : undefined
            }
          >
            {items.length > 0 && (
              <div className="absolute right-1 top-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                <Dropdown
                  trigger={<MoreVertical className="size-4 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300" />}
                  items={items}
                />
              </div>
            )}
            <Icon className={`${ICON_SIZE_CLASSES[size]} ${iconColorClass} flex-shrink-0`} />
            <span className="w-full truncate text-sm font-medium text-gray-900 dark:text-white">{row.name}</span>
          </div>
        )
      })}
    </div>
  )
}
