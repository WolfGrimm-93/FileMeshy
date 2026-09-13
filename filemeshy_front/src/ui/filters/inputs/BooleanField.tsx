import type { BooleanFieldDef, FilterValues } from '../types'

export interface BooleanFieldProps {
  field: BooleanFieldDef
  values: FilterValues
  onChange: (key: string, value: unknown) => void
  autoFocus?: boolean
}

export function BooleanField({ field, values, onChange, autoFocus }: BooleanFieldProps) {
  const inputId = `filter-${field.key}`
  const checked = (values[field.key] as boolean | undefined) ?? false

  return (
    <div className="flex items-center justify-between gap-3">
      <div>
        <label htmlFor={inputId} className="text-sm font-medium text-foreground cursor-pointer">
          {field.label}
        </label>
        {field.description && <p className="text-xs text-muted-foreground">{field.description}</p>}
      </div>
      <button
        id={inputId}
        type="button"
        role="switch"
        aria-checked={checked}
        autoFocus={autoFocus}
        onClick={() => onChange(field.key, checked ? undefined : true)}
        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-hidden focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900 ${
          checked ? 'bg-brand-600' : 'bg-gray-300 dark:bg-gray-600'
        }`}
      >
        <span
          className={`inline-block size-4 transform rounded-full bg-white transition-transform ${
            checked ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </button>
    </div>
  )
}
