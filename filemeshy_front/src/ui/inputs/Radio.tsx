import { forwardRef, type InputHTMLAttributes } from 'react'

export interface RadioOption {
  value: string
  label: string
  description?: string
  price?: string
  disabled?: boolean
}

export interface RadioProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: string
  description?: string
  price?: string
}

export const Radio = forwardRef<HTMLInputElement, RadioProps>(
  ({ label, description, price, className = '', id, ...props }, ref) => {
    const radioId = id || label?.toLowerCase().replace(/\s+/g, '-')

    return (
      <label
        htmlFor={radioId}
        className={`flex cursor-pointer items-center justify-between gap-4 rounded-lg border border-gray-300 bg-white p-3 text-sm font-medium shadow-xs transition-all hover:bg-gray-50 has-checked:border-brand-600 has-checked:ring-1 has-checked:ring-brand-600 dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700 dark:has-checked:border-brand-500 ${className}`}
      >
        <div className="flex-1">
          {label && <p className="text-gray-700 dark:text-gray-300">{label}</p>}
          {description && (
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{description}</p>
          )}
        </div>

        {price && <p className="text-gray-900 dark:text-white">{price}</p>}

        <input ref={ref} type="radio" id={radioId} className="sr-only" {...props} />
      </label>
    )
  }
)

Radio.displayName = 'Radio'

// RadioGroup
export interface RadioGroupProps {
  name: string
  legend?: string
  options: RadioOption[]
  value?: string
  onChange?: (value: string) => void
  error?: string
  helperText?: string
  className?: string
}

export function RadioGroup({
  name,
  legend,
  options,
  value,
  onChange,
  error,
  helperText,
  className = '',
}: RadioGroupProps) {
  return (
    <fieldset className={className}>
      {legend && (
        <legend className="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">
          {legend}
        </legend>
      )}

      <div className="space-y-3">
        {options.map((option) => (
          <Radio
            key={option.value}
            name={name}
            value={option.value}
            label={option.label}
            description={option.description}
            price={option.price}
            checked={value === option.value}
            onChange={(e) => onChange?.(e.target.value)}
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
