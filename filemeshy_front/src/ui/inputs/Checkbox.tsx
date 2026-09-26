import { forwardRef, useId, type InputHTMLAttributes } from 'react'

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: string
  error?: string
  helperText?: string
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  ({ label, error, helperText, className = '', id, ...props }, ref) => {
    // useId garantiza un id único por instancia: derivarlo del label rompía el
    // <label htmlFor> cuando el mismo texto se repite en la página.
    const generatedId = useId()
    const checkboxId = id || generatedId

    const baseCheckboxClasses =
      'size-5 rounded-sm border shadow-xs transition-colors duration-200 focus:outline-hidden focus:ring-2 focus:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50'

    const checkboxStateClasses = error
      ? 'border-red-500 text-red-600 focus:ring-red-500 dark:border-red-500 dark:focus:ring-red-500'
      : 'border-gray-300 text-brand-600 focus:ring-brand-500 dark:border-gray-700 dark:bg-gray-800 dark:focus:ring-brand-500'

    return (
      <div>
        <label htmlFor={checkboxId} className="inline-flex items-center gap-3 cursor-pointer">
          <input
            ref={ref}
            type="checkbox"
            id={checkboxId}
            className={`${baseCheckboxClasses} ${checkboxStateClasses} ${className}`}
            aria-invalid={error ? 'true' : 'false'}
            aria-describedby={
              error ? `${checkboxId}-error` : helperText ? `${checkboxId}-helper` : undefined
            }
            {...props}
          />

          {label && (
            <span className="font-medium text-gray-700 dark:text-gray-300">{label}</span>
          )}
        </label>

        {error && (
          <p className="mt-1 text-sm text-red-600 dark:text-red-500" id={`${checkboxId}-error`}>
            {error}
          </p>
        )}

        {helperText && !error && (
          <p
            className="mt-1 text-sm text-gray-500 dark:text-gray-400"
            id={`${checkboxId}-helper`}
          >
            {helperText}
          </p>
        )}
      </div>
    )
  }
)

Checkbox.displayName = 'Checkbox'

// CheckboxGroup
export interface CheckboxGroupProps {
  legend?: string
  options: { value: string; label: string; disabled?: boolean }[]
  value?: string[]
  onChange?: (value: string[]) => void
  error?: string
  helperText?: string
  className?: string
}

export function CheckboxGroup({
  legend,
  options,
  value = [],
  onChange,
  error,
  helperText,
  className = '',
}: CheckboxGroupProps) {
  const handleChange = (optionValue: string, checked: boolean) => {
    if (!onChange) return

    if (checked) {
      onChange([...value, optionValue])
    } else {
      onChange(value.filter((v) => v !== optionValue))
    }
  }

  return (
    <fieldset className={className}>
      {legend && (
        <legend className="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">
          {legend}
        </legend>
      )}

      <div className="flex flex-col items-start gap-3">
        {options.map((option) => (
          <Checkbox
            key={option.value}
            label={option.label}
            checked={value.includes(option.value)}
            onChange={(e) => handleChange(option.value, e.target.checked)}
            disabled={option.disabled}
          />
        ))}
      </div>

      {error && <p className="mt-2 text-sm text-red-600 dark:text-red-500">{error}</p>}

      {helperText && !error && (
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">{helperText}</p>
      )}
    </fieldset>
  )
}
