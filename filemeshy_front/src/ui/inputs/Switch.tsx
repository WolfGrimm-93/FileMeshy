import React, { forwardRef } from 'react'

export interface SwitchProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'> {
  label?: string
  description?: string
  size?: 'sm' | 'md' | 'lg'
  variant?: 'default' | 'success' | 'warning' | 'danger'
  labelPosition?: 'left' | 'right'
  className?: string
}

const sizeClasses = {
  sm: {
    container: 'h-5 w-9',
    toggle: 'size-4',
    translate: 'translate-x-4',
  },
  md: {
    container: 'h-6 w-11',
    toggle: 'size-5',
    translate: 'translate-x-5',
  },
  lg: {
    container: 'h-7 w-14',
    toggle: 'size-6',
    translate: 'translate-x-7',
  },
}

const variantClasses = {
  default: 'bg-brand-600 dark:bg-brand-700',
  success: 'bg-green-600 dark:bg-green-700',
  warning: 'bg-yellow-600 dark:bg-yellow-700',
  danger: 'bg-red-600 dark:bg-red-700',
}

export const Switch = forwardRef<HTMLInputElement, SwitchProps>(
  (
    {
      label,
      description,
      size = 'md',
      variant = 'default',
      labelPosition = 'right',
      disabled = false,
      checked,
      className = '',
      id,
      ...props
    },
    ref
  ) => {
    const switchId = id || label?.toLowerCase().replace(/\s+/g, '-')

    // El <input> real vive DENTRO del <label> (en vez de hermanos conectados por
    // htmlFor/id) -- bug real encontrado 2026-08-26: sin un `id` o `label` pasado
    // explícito (uso común -- ver UserDetailPage.tsx, EditServiceForm.tsx, etc.),
    // switchId quedaba `undefined`, el <label> se renderizaba sin atributo `for`
    // y, al ser hermano del <input> en vez de contenerlo, clickearlo no
    // disparaba el checkbox -- el toggle se veía normal pero no hacía nada al
    // tocarlo, para cualquier usuario. Anidar el input adentro del label hace
    // que el click funcione siempre, sin depender de que exista un id.
    const switchElement = (
      <div className="relative inline-block">
        <label
          className={`
            block rounded-full transition-colors duration-200
            ${sizeClasses[size].container}
            ${
              disabled
                ? 'cursor-not-allowed opacity-50'
                : 'cursor-pointer focus-within:ring-2 focus-within:ring-brand-500 focus-within:ring-offset-2 dark:focus-within:ring-offset-gray-900'
            }
            ${
              checked
                ? variantClasses[variant]
                : 'bg-gray-300 dark:bg-gray-700'
            }
          `}
        >
          <input
            ref={ref}
            type="checkbox"
            id={switchId}
            checked={checked}
            disabled={disabled}
            className="sr-only"
            {...props}
          />
          <span
            className={`
              absolute top-0.5 left-0.5 rounded-full bg-white transition-transform duration-200
              ${sizeClasses[size].toggle}
              ${checked ? sizeClasses[size].translate : 'translate-x-0'}
            `}
          />
        </label>
      </div>
    )

    if (!label) {
      return switchElement
    }

    return (
      <div className={`flex items-start gap-3 ${className}`}>
        {labelPosition === 'left' && (
          <div className="flex-1">
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
              {label}
            </div>
            {description && (
              <div className="text-sm text-gray-500 dark:text-gray-400">
                {description}
              </div>
            )}
          </div>
        )}

        {switchElement}

        {labelPosition === 'right' && (
          <div className="flex-1">
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
              {label}
            </div>
            {description && (
              <div className="text-sm text-gray-500 dark:text-gray-400">
                {description}
              </div>
            )}
          </div>
        )}
      </div>
    )
  }
)

Switch.displayName = 'Switch'
