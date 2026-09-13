import { ChevronLeft, ChevronRight } from 'lucide-react'

export interface PaginationProps {
  currentPage: number
  totalPages: number
  onPageChange: (page: number) => void
  showPageNumbers?: boolean
  maxPageNumbers?: number
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

export function Pagination({
  currentPage,
  totalPages,
  onPageChange,
  showPageNumbers = true,
  maxPageNumbers = 5,
  size = 'md',
  className = '',
}: PaginationProps) {
  const sizeClasses = {
    sm: 'size-6 text-xs',
    md: 'size-8 text-sm',
    lg: 'size-10 text-base',
  }

  const buttonClass = sizeClasses[size]

  const getPageNumbers = () => {
    const pages: (number | string)[] = []
    
    if (totalPages <= maxPageNumbers) {
      // Show all pages if total is less than max
      return Array.from({ length: totalPages }, (_, i) => i + 1)
    }

    const halfMax = Math.floor(maxPageNumbers / 2)
    let startPage = Math.max(1, currentPage - halfMax)
    let endPage = Math.min(totalPages, currentPage + halfMax)

    // Adjust if we're near the beginning or end
    if (currentPage <= halfMax) {
      endPage = maxPageNumbers
    } else if (currentPage + halfMax >= totalPages) {
      startPage = totalPages - maxPageNumbers + 1
    }

    // Add first page and ellipsis if needed
    if (startPage > 1) {
      pages.push(1)
      if (startPage > 2) {
        pages.push('...')
      }
    }

    // Add middle pages
    for (let i = startPage; i <= endPage; i++) {
      pages.push(i)
    }

    // Add ellipsis and last page if needed
    if (endPage < totalPages) {
      if (endPage < totalPages - 1) {
        pages.push('...')
      }
      pages.push(totalPages)
    }

    return pages
  }

  const handlePrevious = () => {
    if (currentPage > 1) {
      onPageChange(currentPage - 1)
    }
  }

  const handleNext = () => {
    if (currentPage < totalPages) {
      onPageChange(currentPage + 1)
    }
  }

  const pages = getPageNumbers()

  return (
    <nav aria-label="Pagination" className={className}>
      <ul className="flex items-center justify-center gap-1 text-gray-900 dark:text-white">
        {/* Previous Button */}
        <li>
          <button
            onClick={handlePrevious}
            disabled={currentPage === 1}
            className={`${buttonClass} grid place-content-center rounded-sm border border-gray-200 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:hover:bg-gray-800`}
            aria-label="Página anterior"
          >
            <ChevronLeft className="size-4" />
          </button>
        </li>

        {/* Page Numbers */}
        {showPageNumbers &&
          pages.map((page, index) => {
            if (page === '...') {
              return (
                <li key={`ellipsis-${index}`} className="px-2">
                  <span className="text-gray-500 dark:text-gray-400">...</span>
                </li>
              )
            }

            const pageNumber = page as number
            const isActive = pageNumber === currentPage

            return (
              <li key={pageNumber}>
                {isActive ? (
                  <span
                    className={`${buttonClass} flex items-center justify-center rounded-sm border border-brand-600 bg-brand-600 font-medium text-white dark:border-brand-500 dark:bg-brand-500`}
                    aria-current="page"
                  >
                    {pageNumber}
                  </span>
                ) : (
                  <button
                    onClick={() => onPageChange(pageNumber)}
                    className={`${buttonClass} flex items-center justify-center rounded-sm border border-gray-200 font-medium transition-colors hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800`}
                  >
                    {pageNumber}
                  </button>
                )}
              </li>
            )
          })}

        {/* Next Button */}
        <li>
          <button
            onClick={handleNext}
            disabled={currentPage === totalPages}
            className={`${buttonClass} grid place-content-center rounded-sm border border-gray-200 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:hover:bg-gray-800`}
            aria-label="Página siguiente"
          >
            <ChevronRight className="size-4" />
          </button>
        </li>
      </ul>
    </nav>
  )
}

// Simplified Pagination with Input
export interface SimplePaginationProps {
  currentPage: number
  totalPages: number
  onPageChange: (page: number) => void
  className?: string
}

export function SimplePagination({
  currentPage,
  totalPages,
  onPageChange,
  className = '',
}: SimplePaginationProps) {
  const handlePageInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseInt(e.target.value, 10)
    if (!isNaN(value) && value >= 1 && value <= totalPages) {
      onPageChange(value)
    }
  }

  const handlePrevious = () => {
    if (currentPage > 1) {
      onPageChange(currentPage - 1)
    }
  }

  const handleNext = () => {
    if (currentPage < totalPages) {
      onPageChange(currentPage + 1)
    }
  }

  return (
    <nav aria-label="Pagination" className={className}>
      <ul className="flex items-center justify-center gap-2 text-gray-900 dark:text-white">
        {/* Previous Button */}
        <li>
          <button
            onClick={handlePrevious}
            disabled={currentPage === 1}
            className="grid size-8 place-content-center rounded-sm border border-gray-200 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:hover:bg-gray-800"
            aria-label="Página anterior"
          >
            <ChevronLeft className="size-4" />
          </button>
        </li>

        {/* Page Input */}
        <li>
          <label htmlFor="page-input" className="sr-only">
            Página
          </label>
          <input
            id="page-input"
            type="number"
            min="1"
            max={totalPages}
            value={currentPage}
            onChange={handlePageInput}
            className="h-8 w-16 rounded-sm border border-gray-300 text-center text-sm focus:border-brand-500 focus:outline-hidden focus:ring-2 focus:ring-brand-500 dark:border-gray-700 dark:bg-gray-800 dark:focus:border-brand-500"
          />
        </li>

        <li>
          <span className="text-sm text-gray-500 dark:text-gray-400">de {totalPages}</span>
        </li>

        {/* Next Button */}
        <li>
          <button
            onClick={handleNext}
            disabled={currentPage === totalPages}
            className="grid size-8 place-content-center rounded-sm border border-gray-200 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:hover:bg-gray-800"
            aria-label="Página siguiente"
          >
            <ChevronRight className="size-4" />
          </button>
        </li>
      </ul>
    </nav>
  )
}
