import { forwardRef, useState, type InputHTMLAttributes } from 'react'
import { Mail, Eye, EyeOff, Search, Phone, DollarSign, Lock } from 'lucide-react'

export type InputVariant = 'default' | 'filled' | 'outlined' | 'underlined' | 'glass'
export type InputSize = 'sm' | 'md' | 'lg'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  helperText?: string
  icon?: React.ReactNode
  iconPosition?: 'left' | 'right'
  onIconClick?: () => void
  fullWidth?: boolean
  variant?: InputVariant
  inputSize?: InputSize
  rounded?: 'none' | 'sm' | 'md' | 'lg' | 'full'
}

const variantClasses = {
  default: {
    base: 'border bg-white dark:bg-gray-900',
    normal: 'border-gray-200 dark:border-gray-700 focus:border-brand-500 focus:ring-brand-500 dark:focus:ring-brand-600',
    error: 'border-red-500 focus:border-red-500 focus:ring-red-500',
  },
  filled: {
    base: 'border-0 bg-gray-100 dark:bg-gray-800',
    normal: 'focus:bg-white dark:focus:bg-gray-700 focus:ring-brand-500',
    error: 'bg-red-50 dark:bg-red-950 focus:ring-red-500',
  },
  outlined: {
    base: 'border-2 bg-transparent',
    normal: 'border-gray-300 dark:border-gray-700 focus:border-brand-500 focus:ring-0',
    error: 'border-red-500 focus:border-red-600 focus:ring-0',
  },
  underlined: {
    base: 'border-0 border-b-2 bg-transparent rounded-none px-0',
    normal: 'border-gray-300 dark:border-gray-700 focus:border-brand-500 focus:ring-0',
    error: 'border-red-500 focus:border-red-600 focus:ring-0',
  },
  glass: {
    base: 'border bg-white/10 dark:bg-gray-900/10 backdrop-blur-md',
    normal: 'border-white/20 dark:border-gray-700/20 focus:border-brand-500/50 focus:ring-brand-500/50',
    error: 'border-red-500/50 focus:border-red-500 focus:ring-red-500/50',
  },
}

const sizeClasses = {
  sm: 'px-2 py-1.5 text-sm',
  md: 'px-3 py-2 text-sm',
  lg: 'px-4 py-3 text-base',
}

const roundedClasses = {
  none: 'rounded-none',
  sm: 'rounded-xs',
  md: 'rounded-md',
  lg: 'rounded-lg',
  full: 'rounded-full',
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      error,
      helperText,
      icon,
      iconPosition = 'right',
      onIconClick,
      fullWidth = true,
      variant = 'default',
      inputSize = 'md',
      rounded = 'md',
      className = '',
      id,
      ...props
    },
    ref
  ) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, '-')

    const baseInputClasses =
      'shadow-xs transition-all duration-200 focus:outline-hidden focus:ring-2 focus:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50 caret-brand-500 dark:caret-brand-400'

    const variantConfig = variantClasses[variant]
    const inputStateClasses = error
      ? `${variantConfig.base} ${variantConfig.error} text-red-900 dark:text-red-500 placeholder-red-300`
      : `${variantConfig.base} ${variantConfig.normal} text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500`

    const iconPadding = icon
      ? iconPosition === 'left'
        ? variant === 'underlined' ? 'ps-8' : 'ps-11'
        : variant === 'underlined' ? 'pe-8' : 'pe-11'
      : ''

    return (
      <div className={fullWidth ? 'w-full' : ''}>
        {label && (
          <label
            htmlFor={inputId}
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2"
          >
            {label}
          </label>
        )}

        <div className={`relative ${fullWidth ? 'w-full' : ''}`}>
          {icon && iconPosition === 'left' && (
            <span className="absolute inset-y-0 left-0 flex items-center justify-center w-11 pointer-events-none text-gray-500 dark:text-gray-400">
              {icon}
            </span>
          )}

          <input
            ref={ref}
            id={inputId}
            className={`w-full ${baseInputClasses} ${inputStateClasses} ${sizeClasses[inputSize]} ${roundedClasses[rounded]} ${iconPadding} ${className}`}
            aria-invalid={error ? 'true' : 'false'}
            aria-describedby={
              error ? `${inputId}-error` : helperText ? `${inputId}-helper` : undefined
            }
            {...props}
          />

          {icon && iconPosition === 'right' && (
            <button
              type="button"
              tabIndex={-1}
              onClick={onIconClick}
              className={`absolute inset-y-0 right-0 flex items-center justify-center w-11 ${
                onIconClick
                  ? 'cursor-pointer text-gray-700 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200'
                  : 'text-gray-500 dark:text-gray-400 pointer-events-none'
              } transition-colors`}
            >
              {icon}
            </button>
          )}
        </div>

        {error && (
          <p className="mt-1 text-sm text-red-600 dark:text-red-500" id={`${inputId}-error`}>
            {error}
          </p>
        )}

        {helperText && !error && (
          <p
            className="mt-1 text-sm text-gray-500 dark:text-gray-400"
            id={`${inputId}-helper`}
          >
            {helperText}
          </p>
        )}
      </div>
    )
  }
)

Input.displayName = 'Input'

// Email Input
export const EmailInput = forwardRef<HTMLInputElement, Omit<InputProps, 'type' | 'icon' | 'iconPosition'>>(
  (props, ref) => {
    const icon = <Mail className="size-5" />
    return <Input ref={ref} type="email" icon={icon} iconPosition="left" {...props} />
  }
)

EmailInput.displayName = 'EmailInput'

// Password Input with Lock icon on left and Eye toggle on right
export const PasswordInput = forwardRef<HTMLInputElement, Omit<InputProps, 'type' | 'icon' | 'iconPosition' | 'onIconClick'>>(
  (props, ref) => {
    const [showPassword, setShowPassword] = useState(false)
    const {
      className = '',
      inputSize = 'md',
      variant: _variant = 'outlined',
      fullWidth = true,
      rounded = 'md',
      error,
      helperText,
      id,
      ...rest
    } = props

    const inputId = id || 'password'
    const borderClasses = error
      ? 'border-red-500 focus:border-red-600'
      : 'border-gray-300 dark:border-gray-700 focus:border-brand-500'
    const textClasses = error
      ? 'text-red-900 dark:text-red-500 placeholder-red-300'
      : 'text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500'

    return (
      <div className={fullWidth ? 'w-full' : ''}>
        <div className={`relative ${fullWidth ? 'w-full' : ''}`}>
          {/* Lock icon on the left */}
          <span className="absolute inset-y-0 left-0 flex items-center justify-center w-11 pointer-events-none text-gray-500 dark:text-gray-400 z-10">
            <Lock className="size-5" />
          </span>

          <input
            ref={ref}
            id={inputId}
            type={showPassword ? 'text' : 'password'}
            aria-invalid={error ? 'true' : 'false'}
            aria-describedby={error ? `${inputId}-error` : helperText ? `${inputId}-helper` : undefined}
            className={`w-full shadow-xs transition-all duration-200 focus:outline-hidden focus:ring-0 focus:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50 caret-brand-500 dark:caret-brand-400 border-2 bg-transparent ${borderClasses} ${textClasses} ${sizeClasses[inputSize]} ${roundedClasses[rounded]} ps-11 pe-11 ${className}`}
            {...rest}
          />

          {/* Eye toggle on the right */}
          <button
            type="button"
            tabIndex={-1}
            onClick={() => setShowPassword(!showPassword)}
            className="absolute inset-y-0 right-0 flex items-center justify-center w-11 cursor-pointer text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-colors"
            aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
          >
            {showPassword ? <EyeOff className="size-5" /> : <Eye className="size-5" />}
          </button>
        </div>

        {error && (
          <p className="mt-1 text-sm text-red-600 dark:text-red-500" id={`${inputId}-error`}>
            {error}
          </p>
        )}
        {helperText && !error && (
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400" id={`${inputId}-helper`}>
            {helperText}
          </p>
        )}
      </div>
    )
  }
)

PasswordInput.displayName = 'PasswordInput'

// Search Input
export function SearchInput({
  onSearch,
  ...props
}: Omit<InputProps, 'icon' | 'onIconClick'> & {
  onSearch?: () => void
}) {
  const icon = (
    <button
      type="button"
      onClick={onSearch}
      aria-label="Search"
      className="rounded-full p-1.5 text-gray-700 transition-colors hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
    >
      <Search className="size-4" />
    </button>
  )

  return <Input type="text" icon={icon} {...props} />
}

// Phone Input
export function PhoneInput(props: Omit<InputProps, 'type'>) {
  const icon = <Phone className="size-4" />
  return <Input type="tel" icon={icon} {...props} />
}

// Currency Input
export function CurrencyInput({
  currency = '$',
  ...props
}: Omit<InputProps, 'type' | 'iconPosition'> & {
  currency?: string
}) {
  const icon = currency === '$' ? <DollarSign className="size-4" /> : <span className="text-sm font-medium">{currency}</span>

  return <Input type="number" icon={icon} iconPosition="left" step="0.01" min="0" {...props} />
}
