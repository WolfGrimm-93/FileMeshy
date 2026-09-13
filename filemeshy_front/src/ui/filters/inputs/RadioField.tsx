import type { RadioFieldDef, FilterValues } from '../types'

export interface RadioFieldProps {
  field: RadioFieldDef
  values: FilterValues
  onChange: (key: string, value: unknown) => void
  autoFocus?: boolean
}

export function RadioField({ field, values, onChange, autoFocus }: RadioFieldProps) {
  const selected = (values[field.key] as string | undefined) ?? ''
  const groupName = `filter-${field.key}`

  return (
    <fieldset>
      <legend className="mb-1.5 block text-xs font-medium text-muted-foreground">{field.label}</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-2">
        {field.options.map((opt, i) => {
          const inputId = `${groupName}-${opt.value}`
          return (
            <label
              key={opt.value}
              htmlFor={inputId}
              className="flex items-center gap-2 text-sm text-foreground cursor-pointer"
            >
              <input
                id={inputId}
                type="radio"
                name={groupName}
                autoFocus={autoFocus && i === 0}
                checked={selected === opt.value}
                onChange={() => onChange(field.key, opt.value)}
                className="size-4 border-gray-300 text-brand-600 focus:ring-2 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700"
              />
              {opt.label}
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}
