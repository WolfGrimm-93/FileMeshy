/**
 * Tipos del componente reutilizable de filtros (filemeshy_front/src/ui/filters/).
 *
 * Contrato ciego a stores: cada vista resuelve su propio `values`/`onApply`
 * (normalmente delegando a su store de Zustand ya existente); este módulo
 * no importa Zustand ni Axios, solo sabe declarar y renderizar campos.
 */

export interface FilterOption {
  value: string
  label: string
  /** Cantidad de resultados para esta opción (ej. "Pendientes (365)"). Opcional. */
  count?: number
}

interface FilterFieldBase {
  /** Clave dentro de `FilterValues` donde vive el valor de este campo. */
  key: string
  label: string
  /** Texto corto para el chip/badge de filtro activo (si falta, usa `label`). */
  shortLabel?: string
}

export interface SelectFieldDef extends FilterFieldBase {
  type: 'select'
  options: FilterOption[]
  placeholder?: string
}

export interface MultiSelectFieldDef extends FilterFieldBase {
  type: 'multiselect'
  options: FilterOption[]
}

export interface DateRangeFieldDef extends FilterFieldBase {
  type: 'dateRange'
  /** Claves separadas para el valor "desde" y "hasta" dentro de `FilterValues`. */
  fromKey: string
  toKey: string
}

export interface AmountRangeFieldDef extends FilterFieldBase {
  type: 'amountRange'
  fromKey: string
  toKey: string
  /** Prefijo visual del input (ej. "RD$"). Default: "RD$". */
  prefix?: string
}

export interface BooleanFieldDef extends FilterFieldBase {
  type: 'boolean'
  /** Texto de ayuda opcional debajo del label. */
  description?: string
}

export interface RadioFieldDef extends FilterFieldBase {
  type: 'radio'
  options: FilterOption[]
}

/**
 * Discriminada por `type`. Agregar un tipo nuevo acá exige agregar su caso en
 * `inputs/index.tsx` (renderizado) y en `activeFilters.ts` (chip + conteo) —
 * TypeScript marca ambos puntos como error si falta alguno (ver `never` al
 * final de cada switch).
 */
export type FilterFieldDef =
  | SelectFieldDef
  | MultiSelectFieldDef
  | DateRangeFieldDef
  | AmountRangeFieldDef
  | BooleanFieldDef
  | RadioFieldDef

export interface FilterGroup {
  /** Título de sección dentro del modal (ej. "Fechas", "Estado"). Opcional. */
  title?: string
  fields: FilterFieldDef[]
}

/** Valores actuales de filtros: clave declarada por un FilterFieldDef -> valor. */
export type FilterValues = Record<string, unknown>
