import { X } from 'lucide-react'
import type { FilterGroup, FilterValues } from './types'
import { getActiveFilters } from './activeFilters'

export interface FilterChipsProps {
  groups: FilterGroup[]
  values: FilterValues
  /** Se llama una vez por cada clave que compone el chip removido (un rango limpia sus 2 claves). */
  onRemove: (key: string) => void
  className?: string
  /** 'row' (default): en fila, con wrap. 'column': apilados, uno por línea (para cajas angostas al costado). */
  direction?: 'row' | 'column'
}

/** Chips removibles individualmente, uno por filtro con valor activo. */
export function FilterChips({ groups, values, onRemove, className = '', direction = 'row' }: FilterChipsProps) {
  const chips = getActiveFilters(groups, values)

  if (chips.length === 0) return null

  const layoutClass = direction === 'column'
    ? 'flex flex-col items-stretch gap-1.5'
    : 'flex flex-wrap items-center gap-2'

  return (
    <div className={`${layoutClass} ${className}`}>
      {chips.map((chip) => (
        <span
          key={chip.keys.join('|')}
          className="inline-flex items-center justify-between gap-1.5 rounded-full bg-brand-50 px-2.5 py-1 text-xs font-medium text-primary dark:bg-brand-900/20"
        >
          <span className="truncate">{chip.text}</span>
          <button
            type="button"
            onClick={() => chip.keys.forEach(onRemove)}
            aria-label={`Quitar filtro ${chip.text}`}
            className="shrink-0 rounded-full p-0.5 hover:bg-brand-100 dark:hover:bg-brand-900/40"
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
    </div>
  )
}
