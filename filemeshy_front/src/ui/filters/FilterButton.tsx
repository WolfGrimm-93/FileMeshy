import { SlidersHorizontal, FilterX } from 'lucide-react'

export interface FilterButtonProps {
  /** Cantidad de filtros activos -- se muestra como badge y define el estado visual. */
  activeCount: number
  onOpen: () => void
  onClear: () => void
  label?: string
}

/**
 * Botón "Filtrar por" (abre el modal, con badge de contador) + botón separado
 * de "Limpiar" (deshabilitado sin filtros activos). Mismo tono naranja que ya
 * usa TableFilters.tsx para el filtro activo y el sidebar de CxP/CxC.
 */
export function FilterButton({ activeCount, onOpen, onClear, label = 'Filtrar por' }: FilterButtonProps) {
  const hasActive = activeCount > 0

  return (
    <div className="flex items-center gap-1.5">
      <button
        type="button"
        onClick={onOpen}
        className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
          hasActive
            ? 'border-primary bg-brand-50 text-primary dark:bg-brand-900/20'
            : 'border-input text-muted-foreground hover:bg-muted hover:text-foreground'
        }`}
      >
        <SlidersHorizontal className="size-4" />
        {label}
        {hasActive && (
          <span className="ml-0.5 inline-flex size-5 items-center justify-center rounded-full bg-primary text-[11px] font-semibold leading-none text-primary-foreground">
            {activeCount}
          </span>
        )}
      </button>
      <button
        type="button"
        onClick={onClear}
        disabled={!hasActive}
        title="Limpiar filtros"
        aria-label="Limpiar filtros"
        className="flex items-center justify-center rounded-lg border border-input p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-30 disabled:hover:bg-transparent"
      >
        <FilterX className="size-4" />
      </button>
    </div>
  )
}
