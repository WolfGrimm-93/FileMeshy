import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react'

interface TablePaginationProps {
  currentPage: number
  totalPages: number
  totalItems: number
  pageSize: number
  pageSizeOptions?: number[]
  onPageChange: (page: number) => void
  onPageSizeChange?: (size: number) => void
  /** Cantidad mínima de registros para mostrar paginación (default: 50) */
  minItems?: number
}

export function TablePagination({
  currentPage,
  totalPages,
  totalItems,
  pageSize,
  pageSizeOptions = [50, 100, 200, 250],
  onPageChange,
  onPageSizeChange,
  minItems = 50,
}: TablePaginationProps) {
  // No mostrar paginación si los items no superan el mínimo
  if (totalItems <= minItems && totalPages <= 1) return null

  const start = (currentPage - 1) * pageSize + 1
  const end = Math.min(currentPage * pageSize, totalItems)

  const goTo = (page: number) => {
    if (page >= 1 && page <= totalPages && page !== currentPage) {
      onPageChange(page)
    }
  }

  // Generar botones de página (máximo 5)
  const getPages = (): number[] => {
    if (totalPages <= 5) {
      return Array.from({ length: totalPages }, (_, i) => i + 1)
    }
    if (currentPage <= 3) return [1, 2, 3, 4, 5]
    if (currentPage >= totalPages - 2) {
      return Array.from({ length: 5 }, (_, i) => totalPages - 4 + i)
    }
    return [currentPage - 2, currentPage - 1, currentPage, currentPage + 1, currentPage + 2]
  }

  const navBtnClass = (disabled: boolean) =>
    `p-1.5 rounded-sm border transition-colors ${
      disabled
        ? 'border-gray-200 text-gray-300 cursor-not-allowed dark:border-gray-700 dark:text-gray-600'
        : 'border-gray-300 text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-400 dark:hover:bg-gray-800'
    }`

  return (
    <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-2.5 dark:border-gray-700 dark:bg-gray-800">
      {/* Izquierda: info + selector de tamaño */}
      <div className="flex items-center gap-4">
        <span className="text-sm text-gray-600 dark:text-gray-400">
          {start}-{end} de <span className="font-medium text-gray-900 dark:text-white">{totalItems.toLocaleString('es-DO')}</span>
        </span>

        {onPageSizeChange && (
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-gray-500 dark:text-gray-500">Mostrar:</span>
            {pageSizeOptions.map(size => (
              <button
                key={size}
                onClick={() => onPageSizeChange(size)}
                className={`min-w-8 rounded-sm px-1.5 py-0.5 text-xs font-medium transition-colors ${
                  pageSize === size
                    ? 'bg-brand-500 text-white dark:bg-brand-600'
                    : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700'
                }`}
              >
                {size}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Derecha: navegación */}
      <div className="flex items-center gap-1">
        <button
          onClick={() => goTo(1)}
          disabled={currentPage === 1}
          className={navBtnClass(currentPage === 1)}
          title="Primera página"
        >
          <ChevronsLeft className="w-4 h-4" />
        </button>

        <button
          onClick={() => goTo(currentPage - 1)}
          disabled={currentPage === 1}
          className={navBtnClass(currentPage === 1)}
          title="Anterior"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>

        {getPages().map(page => (
          <button
            key={page}
            onClick={() => goTo(page)}
            className={`min-w-8 rounded-sm px-2 py-1 text-xs font-medium transition-colors ${
              currentPage === page
                ? 'bg-brand-500 text-white dark:bg-brand-600'
                : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700'
            }`}
          >
            {page}
          </button>
        ))}

        <button
          onClick={() => goTo(currentPage + 1)}
          disabled={currentPage === totalPages}
          className={navBtnClass(currentPage === totalPages)}
          title="Siguiente"
        >
          <ChevronRight className="w-4 h-4" />
        </button>

        <button
          onClick={() => goTo(totalPages)}
          disabled={currentPage === totalPages}
          className={navBtnClass(currentPage === totalPages)}
          title="Última página"
        >
          <ChevronsRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
