import type { ReactNode } from 'react'
import { useCallback } from 'react'
import { Eye, Edit, Trash2, Printer, Download, CheckCircle, XCircle, ReceiptText } from 'lucide-react'

// =============================================
// TIPOS
// =============================================

export interface Column<T = Record<string, any>> {
  key: keyof T & string
  label: string
  render?: (value: T[keyof T & string], row: T) => ReactNode
  width?: string
  align?: 'left' | 'center' | 'right'
  className?: string
  sortable?: boolean // Aceptado pero ignorado (sorting es backend-side)
}

export interface TableAction<T = Record<string, any>> {
  icon: 'view' | 'edit' | 'delete' | 'print' | 'export' | 'activate' | 'deactivate' | 'nota'
  label: string
  onClick: (row: T) => void
  hidden?: (row: T) => boolean
  color?: string
}

export interface DataTableProps<T extends Record<string, any>> {
  columns?: Column<T>[]
  data: T[]
  actions?: TableAction<T>[]
  rowKey?: keyof T & string
  onRowClick?: (row: T) => void
  loading?: boolean
  emptyMessage?: string
  className?: string
  // Selección (nueva API)
  selectedIds?: Set<string | number>
  onSelectionChange?: (ids: Set<string | number>) => void
  // Compat: props anteriores (aceptadas, algunas ignoradas)
  headers?: Column<T>[]
  enableActions?: boolean
  enableSelection?: boolean
  enableSort?: boolean
  dense?: boolean
  selectedRows?: string[]
  rowIdKey?: keyof T
  getRowClassName?: (row: T) => string
  onRowSelect?: (row: T) => void
  pageSize?: number
  pageSizeOptions?: number[]
  enablePagination?: boolean
  enableInfiniteScroll?: boolean
  enableSearch?: boolean
  enableFilters?: boolean
  searchValue?: string
  onSearchChange?: (value: string) => void
  searchPlaceholder?: string
  statusFilters?: unknown[]
  statusKey?: string
  emptyState?: ReactNode
}

// =============================================
// CONSTANTES
// =============================================

const ACTION_ICONS = {
  view: Eye,
  edit: Edit,
  delete: Trash2,
  print: Printer,
  export: Download,
  activate: CheckCircle,
  deactivate: XCircle,
  nota: ReceiptText,
} as const

const ACTION_COLORS = {
  view: 'text-blue-600 hover:text-blue-700 dark:text-blue-400',
  edit: 'text-brand-600 hover:text-brand-700 dark:text-brand-400',
  delete: 'text-red-600 hover:text-red-700 dark:text-red-400',
  print: 'text-purple-600 hover:text-purple-700 dark:text-purple-400',
  export: 'text-green-600 hover:text-green-700 dark:text-green-400',
  activate: 'text-green-600 hover:text-green-700 dark:text-green-400',
  deactivate: 'text-red-600 hover:text-red-700 dark:text-red-400',
  nota: 'text-amber-600 hover:text-amber-700 dark:text-amber-400',
} as const

const ALIGN_CLASS = {
  left: 'text-left',
  center: 'text-center',
  right: 'text-right',
} as const

// =============================================
// COMPONENTE
// =============================================

export function DataTable<T extends Record<string, any>>({
  columns: columnsProp,
  data,
  actions,
  rowKey = 'id' as keyof T & string,
  onRowClick,
  loading = false,
  emptyMessage = 'No hay datos disponibles',
  className = '',
  selectedIds: selectedIdsProp,
  onSelectionChange: onSelectionChangeProp,
  // Compat con API anterior
  headers,
  enableActions,
  enableSelection,
  selectedRows,
  getRowClassName,
}: DataTableProps<T>) {
  const columns = columnsProp || headers || []
  const showActions = actions && actions.length > 0 && enableActions !== false
  const showSelection = (!!onSelectionChangeProp || !!selectedRows) && enableSelection !== false

  // Compatibilidad: selectedRows (string[]) → selectedIds (Set)
  const selectedIds = selectedIdsProp ?? (selectedRows ? new Set<string | number>(selectedRows) : undefined)
  const onSelectionChange = onSelectionChangeProp

  // ---- Selección ----
  const allSelected = data.length > 0 && selectedIds
    ? data.every(row => selectedIds.has(row[rowKey] as string | number))
    : false

  const someSelected = !allSelected && data.length > 0 && selectedIds
    ? data.some(row => selectedIds.has(row[rowKey] as string | number))
    : false

  const handleSelectAll = useCallback((checked: boolean) => {
    if (!onSelectionChange) return
    const next = new Set(selectedIds)
    for (const row of data) {
      const id = row[rowKey] as string | number
      if (checked) next.add(id)
      else next.delete(id)
    }
    onSelectionChange(next)
  }, [data, rowKey, selectedIds, onSelectionChange])

  const handleSelectRow = useCallback((id: string | number, checked: boolean) => {
    if (!onSelectionChange) return
    const next = new Set(selectedIds)
    if (checked) next.add(id)
    else next.delete(id)
    onSelectionChange(next)
  }, [selectedIds, onSelectionChange])

  // ---- Columnas totales para colspan ----
  const totalCols = columns.length + (showSelection ? 1 : 0) + (showActions ? 1 : 0)

  return (
    <div className={`relative ${className}`}>
      {/* Overlay de carga */}
      {loading && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/60 dark:bg-gray-900/60 rounded-lg">
          <div className="w-8 h-8 border-3 border-brand-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {/* max-[1024px]:min-w-0: si este componente vive dentro de un padre flex, el navegador
          por defecto no lo deja achicarse por debajo del ancho de la tabla (min-width: auto) --
          eso rompe el overflow-x-auto de acá abajo y termina empujando la pagina entera en vez
          de scrollear. min-w-0 fuerza a que SÍ se pueda achicar, para que el scroll horizontal
          funcione en pantallas de 1024px o menos, sin importar el layout que lo contenga. */}
      <div className="overflow-x-auto max-[1024px]:min-w-0 rounded-lg border border-gray-200 dark:border-gray-700">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          {/* HEADER */}
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              {showSelection && (
                <th className="w-10 px-3 py-2">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    ref={el => { if (el) el.indeterminate = someSelected }}
                    onChange={e => handleSelectAll(e.target.checked)}
                    className="w-4 h-4 rounded-sm border-gray-300 text-brand-600 focus:ring-2 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700 cursor-pointer"
                  />
                </th>
              )}

              {columns.map(col => (
                <th
                  key={col.key}
                  style={col.width ? { width: col.width } : undefined}
                  className={`px-3 py-2 text-xs font-semibold uppercase tracking-wider text-gray-600 dark:text-gray-400 ${ALIGN_CLASS[col.align || 'left']} ${col.className || ''}`}
                >
                  {col.label}
                </th>
              ))}

              {showActions && (
                <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-gray-600 dark:text-gray-400 text-right w-24">
                  Acciones
                </th>
              )}
            </tr>
          </thead>

          {/* BODY */}
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {data.length > 0 ? (
              data.map((row, idx) => {
                const id = row[rowKey] as string | number
                const isSelected = selectedIds?.has(id) ?? false
                const striped = idx % 2 !== 0

                const customClass = getRowClassName?.(row)

                return (
                  <tr
                    key={id ?? idx}
                    className={[
                      'transition-colors duration-100',
                      customClass || (striped
                        ? 'bg-gray-50/70 dark:bg-gray-800/40'
                        : 'bg-white dark:bg-gray-900'),
                      isSelected && 'bg-brand-50 dark:bg-brand-900/20',
                      onRowClick && 'cursor-pointer hover:bg-brand-50/60 dark:hover:bg-brand-900/10',
                    ].filter(Boolean).join(' ')}
                    onClick={() => onRowClick?.(row)}
                  >
                    {showSelection && (
                      <td className="w-10 px-3 py-1.5" onClick={e => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={e => handleSelectRow(id, e.target.checked)}
                          className="w-4 h-4 rounded-sm border-gray-300 text-brand-600 focus:ring-2 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700 cursor-pointer"
                        />
                      </td>
                    )}

                    {columns.map(col => (
                      <td
                        key={col.key}
                        className={`px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 whitespace-nowrap ${ALIGN_CLASS[col.align || 'left']} ${col.className || ''}`}
                      >
                        {col.render
                          ? col.render(row[col.key], row)
                          : (row[col.key] as ReactNode) ?? '-'}
                      </td>
                    ))}

                    {showActions && (
                      <td className="px-3 py-1.5 text-right" onClick={e => e.stopPropagation()}>
                        <div className="inline-flex items-center gap-1.5">
                          {actions!.map((action, i) => {
                            if (action.hidden?.(row)) return null
                            const Icon = ACTION_ICONS[action.icon]
                            return (
                              <button
                                key={i}
                                onClick={() => action.onClick(row)}
                                className={`p-1 rounded-sm transition-colors ${action.color || ACTION_COLORS[action.icon]}`}
                                title={action.label}
                              >
                                <Icon className="w-4 h-4" />
                              </button>
                            )
                          })}
                        </div>
                      </td>
                    )}
                  </tr>
                )
              })
            ) : (
              <tr>
                <td colSpan={totalCols} className="py-12 text-center text-sm text-gray-500 dark:text-gray-400">
                  {emptyMessage}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default DataTable
