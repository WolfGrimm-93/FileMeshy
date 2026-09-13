/**
 * Registro extensible de renderizadores por tipo de campo. Agregar un tipo de
 * filtro nuevo significa: (1) sumar su FilterFieldDef en ../types.ts, (2) su
 * componente en este directorio, (3) un caso acá y (4) un caso en
 * ../activeFilters.ts -- nunca tocar FilterModal.tsx ni las vistas que ya
 * consumen el componente.
 */

import type { ReactNode } from 'react'
import type { FilterFieldDef, FilterValues } from '../types'
import { SelectField } from './SelectField'
import { MultiSelectField } from './MultiSelectField'
import { DateRangeField } from './DateRangeField'
import { AmountRangeField } from './AmountRangeField'
import { BooleanField } from './BooleanField'
import { RadioField } from './RadioField'

export function renderFilterField(
  field: FilterFieldDef,
  values: FilterValues,
  onChange: (key: string, value: unknown) => void,
  autoFocus: boolean
): ReactNode {
  switch (field.type) {
    case 'select':
      return <SelectField field={field} values={values} onChange={onChange} autoFocus={autoFocus} />
    case 'multiselect':
      return <MultiSelectField field={field} values={values} onChange={onChange} autoFocus={autoFocus} />
    case 'dateRange':
      return <DateRangeField field={field} values={values} onChange={onChange} autoFocus={autoFocus} />
    case 'amountRange':
      return <AmountRangeField field={field} values={values} onChange={onChange} autoFocus={autoFocus} />
    case 'boolean':
      return <BooleanField field={field} values={values} onChange={onChange} autoFocus={autoFocus} />
    case 'radio':
      return <RadioField field={field} values={values} onChange={onChange} autoFocus={autoFocus} />
    default: {
      // Exhaustividad: un FilterFieldDef nuevo sin registrar acá rompe el build.
      const _exhaustive: never = field
      return _exhaustive
    }
  }
}

export { SelectField, MultiSelectField, DateRangeField, AmountRangeField, BooleanField, RadioField }
