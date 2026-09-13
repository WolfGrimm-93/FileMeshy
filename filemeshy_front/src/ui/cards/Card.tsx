import React from 'react'

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
  variant?: 'default' | 'outlined' | 'elevated' | 'glass' | 'gradient' | 'bordered'
  padding?: 'none' | 'sm' | 'md' | 'lg' | 'xl'
  hoverable?: boolean
  shadow?: 'none' | 'sm' | 'md' | 'lg' | 'xl' | '2xl'
  rounded?: 'none' | 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl'
  className?: string
}

export interface CardHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
  bordered?: boolean
  className?: string
}

export interface CardTitleProps extends React.HTMLAttributes<HTMLHeadingElement> {
  children: React.ReactNode
  as?: 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6'
  className?: string
}

export interface CardDescriptionProps extends React.HTMLAttributes<HTMLParagraphElement> {
  children: React.ReactNode
  className?: string
}

export interface CardContentProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
  className?: string
}

export interface CardFooterProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
  bordered?: boolean
  className?: string
}

const variantClasses = {
  default: 'bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800',
  outlined: 'bg-transparent border-2 border-gray-300 dark:border-gray-700',
  elevated: 'bg-white dark:bg-gray-900 shadow-lg border border-gray-200 dark:border-gray-800',
  glass: 'bg-white/10 dark:bg-gray-900/10 backdrop-blur-md border border-white/20 dark:border-gray-700/20',
  gradient: 'bg-linear-to-br from-white to-gray-50 dark:from-gray-900 dark:to-gray-800 border border-gray-200 dark:border-gray-700',
  bordered: 'bg-white dark:bg-gray-900 border-2 border-brand-200 dark:border-brand-900',
}

const paddingClasses = {
  none: '',
  sm: 'p-3',
  md: 'p-6',
  lg: 'p-8',
  xl: 'p-10',
}

const shadowClasses = {
  none: '',
  sm: 'shadow-xs',
  md: 'shadow-md',
  lg: 'shadow-lg',
  xl: 'shadow-xl',
  '2xl': 'shadow-2xl',
}

const roundedClasses = {
  none: 'rounded-none',
  sm: 'rounded-xs',
  md: 'rounded-md',
  lg: 'rounded-lg',
  xl: 'rounded-xl',
  '2xl': 'rounded-2xl',
  '3xl': 'rounded-3xl',
}

export function Card({
  children,
  variant = 'default',
  padding = 'md',
  hoverable = false,
  shadow = 'none',
  rounded = 'lg',
  className = '',
  ...props
}: CardProps) {
  const baseClasses = 'transition-all duration-200'
  const hoverClasses = hoverable ? 'hover:shadow-xl hover:scale-[1.02] cursor-pointer' : ''

  return (
    <div
      className={`${baseClasses} ${variantClasses[variant]} ${paddingClasses[padding]} ${shadowClasses[shadow]} ${roundedClasses[rounded]} ${hoverClasses} ${className}`}
      {...props}
    >
      {children}
    </div>
  )
}

export function CardHeader({ children, bordered = false, className = '', ...props }: CardHeaderProps) {
  const borderClass = bordered ? 'border-b border-gray-200 dark:border-gray-800 pb-4' : 'pb-4'
  
  return (
    <div className={`flex flex-col space-y-1.5 ${borderClass} ${className}`} {...props}>
      {children}
    </div>
  )
}

export function CardTitle({
  children,
  as: Tag = 'h3',
  className = '',
  ...props
}: CardTitleProps) {
  return (
    <Tag
      className={`text-lg font-semibold leading-none tracking-tight text-gray-900 dark:text-white ${className}`}
      {...props}
    >
      {children}
    </Tag>
  )
}

export function CardDescription({ children, className = '', ...props }: CardDescriptionProps) {
  return (
    <p className={`text-sm text-gray-600 dark:text-gray-400 ${className}`} {...props}>
      {children}
    </p>
  )
}

export function CardContent({ children, className = '', ...props }: CardContentProps) {
  return (
    <div className={`${className}`} {...props}>
      {children}
    </div>
  )
}

export function CardFooter({ children, bordered = false, className = '', ...props }: CardFooterProps) {
  const borderClass = bordered ? 'border-t border-gray-200 dark:border-gray-800 pt-4' : 'pt-4'
  
  return (
    <div className={`flex items-center ${borderClass} ${className}`} {...props}>
      {children}
    </div>
  )
}
