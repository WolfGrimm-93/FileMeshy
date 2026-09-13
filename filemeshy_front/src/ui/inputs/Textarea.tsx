import { forwardRef, type TextareaHTMLAttributes } from 'react'

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  error?: string
  helperText?: string
  fullWidth?: boolean
  showCharCount?: boolean
  maxLength?: number
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  (
    {
      label,
      error,
      helperText,
      fullWidth = true,
      showCharCount = false,
      maxLength,
      className = '',
      id,
      rows = 4,
      value = '',
      ...props
    },
    ref
  ) => {
    const textareaId = id || label?.toLowerCase().replace(/\s+/g, '-')
    const currentLength = String(value).length

    const baseTextareaClasses =
      'rounded-md border shadow-xs transition-colors duration-200 focus:outline-hidden focus:ring-2 focus:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50 sm:text-sm resize-none'

    const textareaStateClasses = error
      ? 'border-red-500 text-red-900 placeholder-red-300 focus:border-red-500 focus:ring-red-500 dark:border-red-500 dark:text-red-500 dark:focus:border-red-500'
      : 'border-gray-300 text-gray-900 placeholder-gray-400 focus:border-brand-500 focus:ring-brand-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:placeholder-gray-500 dark:focus:border-brand-500'

    return (
      <div className={fullWidth ? 'w-full' : ''}>
        {label && (
          <label
            htmlFor={textareaId}
            className="block text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            {label}
          </label>
        )}

        <textarea
          ref={ref}
          id={textareaId}
          rows={rows}
          maxLength={maxLength}
          value={value}
          className={`${baseTextareaClasses} ${textareaStateClasses} ${label ? 'mt-1' : ''} ${className}`}
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={
            error ? `${textareaId}-error` : helperText ? `${textareaId}-helper` : undefined
          }
          {...props}
        />

        <div className="mt-1 flex items-center justify-between">
          <div className="flex-1">
            {error && (
              <p className="text-sm text-red-600 dark:text-red-500" id={`${textareaId}-error`}>
                {error}
              </p>
            )}

            {helperText && !error && (
              <p
                className="text-sm text-gray-500 dark:text-gray-400"
                id={`${textareaId}-helper`}
              >
                {helperText}
              </p>
            )}
          </div>

          {showCharCount && maxLength && (
            <p
              className={`text-xs ${
                currentLength > maxLength
                  ? 'text-red-600 dark:text-red-500'
                  : 'text-gray-500 dark:text-gray-400'
              }`}
            >
              {currentLength}/{maxLength}
            </p>
          )}
        </div>
      </div>
    )
  }
)

Textarea.displayName = 'Textarea'
