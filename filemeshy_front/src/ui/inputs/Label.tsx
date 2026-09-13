import React from 'react'

export interface LabelProps extends React.LabelHTMLAttributes<HTMLLabelElement> {
  children: React.ReactNode
  required?: boolean
  disabled?: boolean
  className?: string
}

export function Label({
  children,
  required = false,
  disabled = false,
  className = '',
  ...props
}: LabelProps) {
  const baseClasses = 'block text-sm font-medium transition-colors duration-200'
  const stateClasses = disabled
    ? 'text-gray-400 dark:text-gray-600 cursor-not-allowed'
    : 'text-gray-700 dark:text-gray-300'

  return (
    <label className={`${baseClasses} ${stateClasses} ${className}`} {...props}>
      {children}
      {required && <span className="ml-1 text-red-500" aria-label="required">*</span>}
    </label>
  )
}
