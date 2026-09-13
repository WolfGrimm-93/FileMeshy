/**
 * Resuelve qué campos de una config de filtros tienen valor activo, con el
 * texto legible (label + valor) que van a mostrar los chips y el contador del
 * botón "Filtrar por". Único punto de verdad para "¿qué cuenta como filtro
 * activo?" -- FilterButton y FilterChips comparten esta lógica en vez de
 * duplicar el switch por tipo cada uno.
 */

import { formatDate } from '@/shared/utils/dates'

/** Fecha compacta para chips: "01/06" (sin año, para que el chip quede corto). */
function formatChipDate(dateStr: string): string {
  return formatDate(dateStr, { day: '2-digit', month: '2-digit' }) ?? dateStr
}
import type { FilterFieldDef, FilterGroup, FilterValues } from './types'

export interface ActiveFilter {
  /** Clave(s) de FilterValues que se limpian juntas al remover este filtro
   *  (dateRange/amountRange limpian "desde" y "hasta" como una unidad). */
  keys: string[]
  text: string
}

function resolveField(field: FilterFieldDef, values: FilterValues): ActiveFilter | null {
  const label = field.shortLabel ?? field.label
  switch (field.type) {
    case 'select':
    case 'radio': {
      const value = values[field.key] as string | undefined
      if (!value) return null
      const optionLabel = field.options.find(o => o.value === value)?.label ?? value
      return { keys: [field.key], text: `${label}: ${optionLabel}` }
    }
    case 'multiselect': {
      const selected = values[field.key] as string[] | undefined
      if (!selected || selected.length === 0) return null
      const labels = selected.map(v => field.options.find(o => o.value === v)?.label ?? v)
      return { keys: [field.key], text: `${label}: ${labels.join(', ')}` }
    }
    case 'boolean': {
      const value = values[field.key] as boolean | undefined
      if (!value) return null
      return { keys: [field.key], text: label }
    }
    case 'dateRange': {
      const from = values[field.fromKey] as string | undefined
      const to = values[field.toKey] as string | undefined
      if (!from && !to) return null
      const fromText = from ? formatChipDate(from) : undefined
      const toText = to ? formatChipDate(to) : undefined
      const text = fromText && toText
        ? `${label}: ${fromText} – ${toText}`
        : fromText
          ? `${label}: desde ${fromText}`
          : `${label}: hasta ${toText}`
      return { keys: [field.fromKey, field.toKey], text }
    }
    case 'amountRange': {
      const from = values[field.fromKey] as number | undefined
      const to = values[field.toKey] as number | undefined
      if (from === undefined && to === undefined) return null
      const prefix = field.prefix ?? 'RD$'
      const text = from !== undefined && to !== undefined
        ? `${label}: ${prefix}${from} – ${prefix}${to}`
        : from !== undefined
          ? `${label}: desde ${prefix}${from}`
          : `${label}: hasta ${prefix}${to}`
      return { keys: [field.fromKey, field.toKey], text }
    }
    default: {
      const _exhaustive: never = field
      return _exhaustive
    }
  }
}

export function getActiveFilters(groups: FilterGroup[], values: FilterValues): ActiveFilter[] {
  return groups
    .flatMap(g => g.fields)
    .map(field => resolveField(field, values))
    .filter((f): f is ActiveFilter => f !== null)
}

/** Para el badge del botón "Filtrar por". Cuenta filtros (no claves): un rango cuenta 1. */
export function countActiveFilters(groups: FilterGroup[], values: FilterValues): number {
  return getActiveFilters(groups, values).length
}
