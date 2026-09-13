import type { MultiSelectFieldDef, FilterValues } from '../types'

export interface MultiSelectFieldProps {
  field: MultiSelectFieldDef
  values: FilterValues
  onChange: (key: string, value: unknown) => void
  autoFocus?: boolean
}

export function MultiSelectField({ field, values, onChange, autoFocus }: MultiSelectFieldProps) {
  const selected = (values[field.key] as string[] | undefined) ?? []

  const toggle = (optionValue: string) => {
    const next = selected.includes(optionValue)
      ? selected.filter((v) => v !== optionValue)
      : [...selected, optionValue]
    onChange(field.key, next.length > 0 ? next : undefined)
  }

  return (
    <fieldset>
      <legend className="mb-1.5 block text-xs font-medium text-muted-foreground">{field.label}</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-2">
        {field.options.map((opt, i) => {
          const inputId = `filter-${field.key}-${opt.value}`
          return (
            <label
              key={opt.value}
              htmlFor={inputId}
              className="flex items-center gap-2 text-sm text-foreground cursor-pointer"
            >
              <input
                id={inputId}
                type="checkbox"
                autoFocus={autoFocus && i === 0}
                checked={selected.includes(opt.value)}
                onChange={() => toggle(opt.value)}
                className="size-4 rounded-sm border-gray-300 text-brand-600 focus:ring-2 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700"
              />
              {opt.label}
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}
