import React from 'react'

export interface FieldProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
  className?: string
}

export interface FieldGroupProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
  direction?: 'vertical' | 'horizontal'
  spacing?: 'sm' | 'md' | 'lg'
  className?: string
}

export interface FieldLabelProps extends React.LabelHTMLAttributes<HTMLLabelElement> {
  children: React.ReactNode
  required?: boolean
  disabled?: boolean
  className?: string
}

export interface FieldDescriptionProps extends React.HTMLAttributes<HTMLParagraphElement> {
  children: React.ReactNode
  className?: string
}

export interface FieldErrorProps extends React.HTMLAttributes<HTMLParagraphElement> {
  children: React.ReactNode
  className?: string
}

const directionClasses = {
  vertical: 'flex-col',
  horizontal: 'flex-row items-center',
}

const spacingClasses = {
  sm: 'gap-1',
  md: 'gap-2',
  lg: 'gap-4',
}

export function Field({ children, className = '', ...props }: FieldProps) {
  return (
    <div className={`space-y-2 ${className}`} {...props}>
      {children}
    </div>
  )
}

export function FieldGroup({
  children,
  direction = 'vertical',
  spacing = 'md',
  className = '',
  ...props
}: FieldGroupProps) {
  return (
    <div
      className={`flex ${directionClasses[direction]} ${spacingClasses[spacing]} ${className}`}
      {...props}
    >
      {children}
    </div>
  )
}

export function FieldLabel({
  children,
  required = false,
  disabled = false,
  className = '',
  ...props
}: FieldLabelProps) {
  const baseClasses = 'block text-sm font-medium transition-colors duration-200'
  const stateClasses = disabled
    ? 'text-gray-400 dark:text-gray-600 cursor-not-allowed'
    : 'text-gray-700 dark:text-gray-300'

  return (
    <label className={`${baseClasses} ${stateClasses} ${className}`} {...props}>
      {children}
      {required && (
        <span className="ml-1 text-red-500" aria-label="required">
          *
        </span>
      )}
    </label>
  )
}

export function FieldDescription({ children, className = '', ...props }: FieldDescriptionProps) {
  return (
    <p className={`text-sm text-gray-600 dark:text-gray-400 ${className}`} {...props}>
      {children}
    </p>
  )
}

export function FieldError({ children, className = '', ...props }: FieldErrorProps) {
  return (
    <p
      className={`text-sm text-red-600 dark:text-red-400 ${className}`}
      role="alert"
      {...props}
    >
      {children}
    </p>
  )
}
