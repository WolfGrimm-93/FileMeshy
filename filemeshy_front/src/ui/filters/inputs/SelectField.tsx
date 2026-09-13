import type { SelectFieldDef, FilterValues } from '../types'

export interface SelectFieldProps {
  field: SelectFieldDef
  values: FilterValues
  onChange: (key: string, value: unknown) => void
  autoFocus?: boolean
}

export function SelectField({ field, values, onChange, autoFocus }: SelectFieldProps) {
  const inputId = `filter-${field.key}`
  const value = (values[field.key] as string | undefined) ?? ''

  return (
    <div>
      <label htmlFor={inputId} className="mb-1 block text-xs font-medium text-muted-foreground">
        {field.label}
      </label>
      <select
        id={inputId}
        autoFocus={autoFocus}
        value={value}
        onChange={(e) => onChange(field.key, e.target.value || undefined)}
        className="w-full rounded-lg border border-input bg-background px-3 py-1.5 text-sm text-foreground focus:border-transparent focus:outline-hidden focus:ring-2 focus:ring-brand-500"
      >
        <option value="">{field.placeholder ?? 'Todos'}</option>
        {field.options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.count !== undefined ? `${opt.label} (${opt.count})` : opt.label}
          </option>
        ))}
      </select>
    </div>
  )
}
