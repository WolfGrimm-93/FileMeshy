import React from 'react'
import { Check, Trash2, Edit2, Plus, Loader2 } from 'lucide-react'

export type ButtonVariant = 'primary' | 'secondary' | 'success' | 'danger' | 'warning' | 'ghost' | 'outline' | 'link' | 'gradient'
export type ButtonSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl'
export type ButtonStyle = 'solid' | 'outline' | 'ghost' | 'gradient' | 'soft' | 'glass'

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  buttonStyle?: ButtonStyle
  fullWidth?: boolean
  rounded?: 'sm' | 'md' | 'lg' | 'full' | 'none'
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
  isLoading?: boolean
  loadingText?: string
  shadow?: 'none' | 'sm' | 'md' | 'lg' | 'xl'
  children: React.ReactNode
}

// Configuración de variantes por estilo
const styleVariantClasses = {
  solid: {
    primary: 'bg-brand-600 text-white hover:bg-brand-700 focus:ring-brand-500 dark:bg-brand-700 dark:hover:bg-brand-800',
    secondary: 'bg-gray-600 text-white hover:bg-gray-700 focus:ring-gray-500 dark:bg-gray-700 dark:hover:bg-gray-800',
    success: 'bg-green-600 text-white hover:bg-green-700 focus:ring-green-500 dark:bg-green-700 dark:hover:bg-green-800',
    danger: 'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500 dark:bg-red-700 dark:hover:bg-red-800',
    warning: 'bg-yellow-600 text-white hover:bg-yellow-700 focus:ring-yellow-500 dark:bg-yellow-700 dark:hover:bg-yellow-800',
    ghost: 'text-gray-700 hover:bg-gray-100 focus:ring-gray-500 dark:text-gray-300 dark:hover:bg-gray-800',
    outline: 'border-2 border-gray-300 bg-white text-gray-700 hover:bg-gray-50 focus:ring-gray-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700',
    link: 'text-brand-600 hover:text-brand-700 hover:underline focus:ring-brand-500 dark:text-brand-500 dark:hover:text-brand-600',
    gradient: 'bg-linear-to-r from-brand-500 to-pink-500 text-white hover:from-brand-600 hover:to-pink-600 focus:ring-brand-500',
  },
  outline: {
    primary: 'border-2 border-brand-600 text-brand-600 hover:bg-brand-50 focus:ring-brand-500 dark:border-brand-500 dark:text-brand-500 dark:hover:bg-brand-950',
    secondary: 'border-2 border-gray-600 text-gray-700 hover:bg-gray-50 focus:ring-gray-500 dark:border-gray-500 dark:text-gray-400 dark:hover:bg-gray-900',
    success: 'border-2 border-green-600 text-green-600 hover:bg-green-50 focus:ring-green-500 dark:border-green-500 dark:text-green-500 dark:hover:bg-green-950',
    danger: 'border-2 border-red-600 text-red-600 hover:bg-red-50 focus:ring-red-500 dark:border-red-500 dark:text-red-500 dark:hover:bg-red-950',
    warning: 'border-2 border-yellow-600 text-yellow-600 hover:bg-yellow-50 focus:ring-yellow-500 dark:border-yellow-500 dark:text-yellow-500 dark:hover:bg-yellow-950',
    ghost: 'border-2 border-gray-300 text-gray-700 hover:bg-gray-50 focus:ring-gray-500 dark:border-gray-600 dark:text-gray-400 dark:hover:bg-gray-900',
    outline: 'border-2 border-gray-300 text-gray-700 hover:bg-gray-50 focus:ring-gray-500 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-900',
    link: 'border-2 border-transparent text-brand-600 hover:border-brand-600 focus:ring-brand-500 dark:text-brand-500',
    gradient: 'border-2 border-transparent bg-linear-to-r from-brand-500 to-pink-500 bg-clip-text text-transparent hover:from-brand-600 hover:to-pink-600',
  },
  ghost: {
    primary: 'text-brand-600 hover:bg-brand-50 focus:ring-brand-500 dark:text-brand-500 dark:hover:bg-brand-950',
    secondary: 'text-gray-700 hover:bg-gray-100 focus:ring-gray-500 dark:text-gray-400 dark:hover:bg-gray-800',
    success: 'text-green-600 hover:bg-green-50 focus:ring-green-500 dark:text-green-500 dark:hover:bg-green-950',
    danger: 'text-red-600 hover:bg-red-50 focus:ring-red-500 dark:text-red-500 dark:hover:bg-red-950',
    warning: 'text-yellow-600 hover:bg-yellow-50 focus:ring-yellow-500 dark:text-yellow-500 dark:hover:bg-yellow-950',
    ghost: 'text-gray-700 hover:bg-gray-100 focus:ring-gray-500 dark:text-gray-400 dark:hover:bg-gray-800',
    outline: 'text-gray-700 hover:bg-gray-100 focus:ring-gray-500 dark:text-gray-300 dark:hover:bg-gray-800',
    link: 'text-brand-600 hover:bg-brand-50 hover:underline focus:ring-brand-500 dark:text-brand-500 dark:hover:bg-brand-950',
    gradient: 'bg-linear-to-r from-brand-500 to-pink-500 bg-clip-text text-transparent hover:from-brand-600 hover:to-pink-600',
  },
  gradient: {
    primary: 'bg-linear-to-r from-brand-500 to-red-500 text-white hover:from-brand-600 hover:to-red-600 focus:ring-brand-500',
    secondary: 'bg-linear-to-r from-gray-500 to-gray-700 text-white hover:from-gray-600 hover:to-gray-800 focus:ring-gray-500',
    success: 'bg-linear-to-r from-green-500 to-emerald-500 text-white hover:from-green-600 hover:to-emerald-600 focus:ring-green-500',
    danger: 'bg-linear-to-r from-red-500 to-rose-500 text-white hover:from-red-600 hover:to-rose-600 focus:ring-red-500',
    warning: 'bg-linear-to-r from-yellow-500 to-brand-500 text-white hover:from-yellow-600 hover:to-brand-600 focus:ring-yellow-500',
    ghost: 'bg-linear-to-r from-gray-400 to-gray-600 bg-clip-text text-transparent hover:from-gray-500 hover:to-gray-700',
    outline: 'bg-linear-to-r from-blue-500 to-purple-500 text-white hover:from-blue-600 hover:to-purple-600 focus:ring-blue-500',
    link: 'bg-linear-to-r from-brand-500 to-pink-500 bg-clip-text text-transparent hover:from-brand-600 hover:to-pink-600',
    gradient: 'bg-linear-to-r from-purple-500 via-pink-500 to-brand-500 text-white hover:from-purple-600 hover:via-pink-600 hover:to-brand-600 focus:ring-pink-500',
  },
  soft: {
    primary: 'bg-brand-100 text-brand-700 hover:bg-brand-200 focus:ring-brand-500 dark:bg-brand-950 dark:text-brand-400 dark:hover:bg-brand-900',
    secondary: 'bg-gray-100 text-gray-700 hover:bg-gray-200 focus:ring-gray-500 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700',
    success: 'bg-green-100 text-green-700 hover:bg-green-200 focus:ring-green-500 dark:bg-green-950 dark:text-green-400 dark:hover:bg-green-900',
    danger: 'bg-red-100 text-red-700 hover:bg-red-200 focus:ring-red-500 dark:bg-red-950 dark:text-red-400 dark:hover:bg-red-900',
    warning: 'bg-yellow-100 text-yellow-700 hover:bg-yellow-200 focus:ring-yellow-500 dark:bg-yellow-950 dark:text-yellow-400 dark:hover:bg-yellow-900',
    ghost: 'bg-gray-100 text-gray-700 hover:bg-gray-200 focus:ring-gray-500 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700',
    outline: 'bg-blue-100 text-blue-700 hover:bg-blue-200 focus:ring-blue-500 dark:bg-blue-950 dark:text-blue-400 dark:hover:bg-blue-900',
    link: 'bg-brand-100 text-brand-700 hover:bg-brand-200 hover:underline focus:ring-brand-500 dark:bg-brand-950 dark:text-brand-400',
    gradient: 'bg-linear-to-r from-brand-100 to-pink-100 text-brand-700 hover:from-brand-200 hover:to-pink-200 dark:from-brand-950 dark:to-pink-950 dark:text-brand-400',
  },
  glass: {
    primary: 'bg-brand-500/10 backdrop-blur-xs border border-brand-500/20 text-brand-700 hover:bg-brand-500/20 focus:ring-brand-500 dark:text-brand-400',
    secondary: 'bg-gray-500/10 backdrop-blur-xs border border-gray-500/20 text-gray-700 hover:bg-gray-500/20 focus:ring-gray-500 dark:text-gray-400',
    success: 'bg-green-500/10 backdrop-blur-xs border border-green-500/20 text-green-700 hover:bg-green-500/20 focus:ring-green-500 dark:text-green-400',
    danger: 'bg-red-500/10 backdrop-blur-xs border border-red-500/20 text-red-700 hover:bg-red-500/20 focus:ring-red-500 dark:text-red-400',
    warning: 'bg-yellow-500/10 backdrop-blur-xs border border-yellow-500/20 text-yellow-700 hover:bg-yellow-500/20 focus:ring-yellow-500 dark:text-yellow-400',
    ghost: 'bg-white/10 backdrop-blur-xs border border-white/20 text-gray-700 hover:bg-white/20 focus:ring-gray-500 dark:text-gray-400',
    outline: 'bg-blue-500/10 backdrop-blur-xs border border-blue-500/20 text-blue-700 hover:bg-blue-500/20 focus:ring-blue-500 dark:text-blue-400',
    link: 'bg-brand-500/10 backdrop-blur-xs text-brand-700 hover:bg-brand-500/20 hover:underline focus:ring-brand-500 dark:text-brand-400',
    gradient: 'bg-linear-to-r from-brand-500/10 to-pink-500/10 backdrop-blur-xs border border-white/20 text-brand-700 hover:from-brand-500/20 hover:to-pink-500/20 dark:text-brand-400',
  },
}

const sizeClasses = {
  xs: 'px-2.5 py-1.5 text-xs gap-1.5',
  sm: 'px-3 py-2 text-sm gap-2',
  md: 'px-4 py-2.5 text-sm gap-2',
  lg: 'px-5 py-3 text-base gap-2.5',
  xl: 'px-6 py-3.5 text-base gap-3',
}

const roundedClasses = {
  none: 'rounded-none',
  sm: 'rounded-xs',
  md: 'rounded-md',
  lg: 'rounded-lg',
  full: 'rounded-full',
}

const shadowClasses = {
  none: '',
  sm: 'shadow-xs',
  md: 'shadow-md',
  lg: 'shadow-lg',
  xl: 'shadow-xl',
}

export function Button({
  variant = 'primary',
  size = 'md',
  buttonStyle = 'solid',
  fullWidth = false,
  rounded = 'md',
  leftIcon,
  rightIcon,
  isLoading = false,
  loadingText,
  shadow = 'none',
  disabled,
  children,
  className = '',
  ...props
}: ButtonProps) {
  const baseClasses =
    'inline-flex items-center justify-center font-medium transition-all duration-200 focus:outline-hidden focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed dark:focus:ring-offset-gray-900'

  const variantClass = styleVariantClasses[buttonStyle][variant] || styleVariantClasses.solid[variant]

  return (
    <button
      className={`${baseClasses} ${variantClass} ${sizeClasses[size]} ${roundedClasses[rounded]} ${shadowClasses[shadow]} ${
        fullWidth ? 'w-full' : ''
      } ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <>
          <LoadingSpinner size={size} />
          <span>{loadingText || 'Cargando...'}</span>
        </>
      ) : (
        <>
          {leftIcon && <span className="shrink-0">{leftIcon}</span>}
          <span>{children}</span>
          {rightIcon && <span className="shrink-0">{rightIcon}</span>}
        </>
      )}
    </button>
  )
}

// Botones preconfigurados para acciones comunes
export function SaveButton(props: Omit<ButtonProps, 'variant' | 'leftIcon'>) {
  return (
    <Button
      variant="primary"
      leftIcon={<Check className="size-5" />}
      {...props}
    >
      {props.children || 'Guardar'}
    </Button>
  )
}

export function DeleteButton(props: Omit<ButtonProps, 'variant' | 'leftIcon'>) {
  return (
    <Button
      variant="danger"
      leftIcon={<Trash2 className="size-5" />}
      {...props}
    >
      {props.children || 'Eliminar'}
    </Button>
  )
}

export function EditButton(props: Omit<ButtonProps, 'variant' | 'leftIcon'>) {
  return (
    <Button
      variant="secondary"
      leftIcon={<Edit2 className="size-5" />}
      {...props}
    >
      {props.children || 'Editar'}
    </Button>
  )
}

export function AddButton(props: Omit<ButtonProps, 'variant' | 'leftIcon'>) {
  return (
    <Button
      variant="primary"
      leftIcon={<Plus className="size-5" />}
      {...props}
    >
      {props.children || 'Agregar'}
    </Button>
  )
}

export function CancelButton(props: Omit<ButtonProps, 'variant'>) {
  return (
    <Button variant="ghost" {...props}>
      {props.children || 'Cancelar'}
    </Button>
  )
}

// Spinner de carga
function LoadingSpinner({ size }: { size: ButtonSize }) {
  const spinnerSizes = {
    xs: 'size-3',
    sm: 'size-4',
    md: 'size-4',
    lg: 'size-5',
    xl: 'size-5',
  }

  return <Loader2 className={`animate-spin ${spinnerSizes[size]}`} />
}
