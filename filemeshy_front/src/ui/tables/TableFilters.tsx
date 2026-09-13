import type { ReactNode } from 'react'
import { Search } from 'lucide-react'
import { Input } from '@/ui/inputs/Input'

interface StatusOption {
  value: string | number | undefined
  label: string
}

export interface StatusFilter {
  key: string
  label: string
  value?: string | number
  count?: number
}

interface TableFiltersProps {
  // Búsqueda
  enableSearch?: boolean
  searchValue?: string
  onSearchChange?: (value: string) => void
  searchPlaceholder?: string

  // Filtros
  enableFilters?: boolean
  statusFilters?: StatusFilter[]
  activeFilter?: string | null
  onFilterChange?: (value: unknown) => void
  totalItems?: number

  // Status dropdown (alternativa a statusFilters)
  statusValue?: string | number | undefined
  onStatusChange?: (value: string | number | undefined) => void
  statusOptions?: StatusOption[]

  // Extra
  extraFilters?: ReactNode
}

export function TableFilters({
  enableSearch = false,
  searchValue = '',
  onSearchChange,
  searchPlaceholder = 'Buscar...',
  enableFilters = false,
  statusFilters = [],
  activeFilter = null,
  onFilterChange,
  totalItems: _totalItems = 0,
  statusValue,
  onStatusChange,
  statusOptions = [],
  extraFilters,
}: TableFiltersProps) {
  const showStatusDropdown = statusOptions && statusOptions.length > 0 && onStatusChange

  if (!enableSearch && !enableFilters && !showStatusDropdown) {
    return null
  }

  const handleFilterClick = (filterKey: string) => {
    if (onFilterChange) {
      onFilterChange(filterKey)
    }
  }

  return (
    <div className="flex items-center gap-3">
      {/* Búsqueda */}
      {enableSearch && (
        <div className="flex-1">
          <Input
            type="text"
            value={searchValue}
            onChange={(e) => onSearchChange?.(e.target.value)}
            placeholder={searchPlaceholder}
            icon={<Search className="size-4" />}
            iconPosition="left"
          />
        </div>
      )}

      {/* Dropdown de estatus (para usuarios/roles) */}
      {showStatusDropdown && (
        <select
          value={statusValue}
          onChange={(e) =>
            onStatusChange(
              e.target.value === 'undefined' ? undefined : e.target.value
            )
          }
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 text-sm"
        >
          {statusOptions.map((option) => (
            <option key={String(option.value)} value={String(option.value)}>
              {option.label}
            </option>
          ))}
        </select>
      )}

      {/* Filtros de estado (buttons) */}
      {enableFilters && statusFilters && statusFilters.length > 0 && (
        <div className="flex items-center gap-2 text-sm">
          {statusFilters.map((filter, index) => (
            <span key={filter.key}>
              {index > 0 && (
                <span className="text-gray-300 dark:text-gray-600 mx-1">|</span>
              )}
              <button
                onClick={() => handleFilterClick(filter.key)}
                className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                  activeFilter === filter.key
                    ? 'bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-400'
                    : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800'
                }`}
              >
                {filter.label} {filter.count !== undefined && `(${filter.count})`}
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Filtros extras */}
      {extraFilters}
    </div>
  )
}
