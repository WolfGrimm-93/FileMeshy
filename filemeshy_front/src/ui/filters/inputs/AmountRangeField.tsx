import type { AmountRangeFieldDef, FilterValues } from '../types'

export interface AmountRangeFieldProps {
  field: AmountRangeFieldDef
  values: FilterValues
  onChange: (key: string, value: unknown) => void
  autoFocus?: boolean
}

function parseAmount(raw: string): number | undefined {
  if (raw === '') return undefined
  const n = Number(raw)
  return Number.isNaN(n) ? undefined : n
}

export function AmountRangeField({ field, values, onChange, autoFocus }: AmountRangeFieldProps) {
  const fromId = `filter-${field.fromKey}`
  const toId = `filter-${field.toKey}`
  const fromValue = values[field.fromKey] as number | undefined
  const toValue = values[field.toKey] as number | undefined
  const prefix = field.prefix ?? 'RD$'

  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-muted-foreground">{field.label}</p>
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <label htmlFor={fromId} className="sr-only">
            {field.label} — mínimo
          </label>
          <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-xs text-muted-foreground">
            {prefix}
          </span>
          <input
            id={fromId}
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0"
            autoFocus={autoFocus}
            placeholder="Mínimo"
            value={fromValue ?? ''}
            onChange={(e) => onChange(field.fromKey, parseAmount(e.target.value))}
            className="w-full rounded-lg border border-input bg-background py-1.5 pl-10 pr-3 text-sm text-foreground focus:border-transparent focus:outline-hidden focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <span className="text-xs text-muted-foreground">—</span>
        <div className="relative flex-1">
          <label htmlFor={toId} className="sr-only">
            {field.label} — máximo
          </label>
          <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-xs text-muted-foreground">
            {prefix}
          </span>
          <input
            id={toId}
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0"
            placeholder="Máximo"
            value={toValue ?? ''}
            onChange={(e) => onChange(field.toKey, parseAmount(e.target.value))}
            className="w-full rounded-lg border border-input bg-background py-1.5 pl-10 pr-3 text-sm text-foreground focus:border-transparent focus:outline-hidden focus:ring-2 focus:ring-brand-500"
          />
        </div>
      </div>
    </div>
  )
}
