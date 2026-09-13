/**
 * Barrel export del componente reutilizable de filtros.
 * Ver types.ts para el contrato de declaración de filtros por vista.
 */

export type {
  FilterOption,
  SelectFieldDef,
  MultiSelectFieldDef,
  DateRangeFieldDef,
  AmountRangeFieldDef,
  BooleanFieldDef,
  RadioFieldDef,
  FilterFieldDef,
  FilterGroup,
  FilterValues,
} from './types'

export { FilterModal } from './FilterModal'
export type { FilterModalProps } from './FilterModal'

export { FilterButton } from './FilterButton'
export type { FilterButtonProps } from './FilterButton'

export { FilterChips } from './FilterChips'
export type { FilterChipsProps } from './FilterChips'

export { getActiveFilters, countActiveFilters } from './activeFilters'
export type { ActiveFilter } from './activeFilters'
