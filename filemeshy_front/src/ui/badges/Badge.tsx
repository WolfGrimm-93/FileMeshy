import React from 'react'
import { X } from 'lucide-react'

export type BadgeVariant = 'primary' | 'success' | 'danger' | 'warning' | 'info' | 'purple' | 'gray' | 'pink' | 'indigo' | 'cyan' | 'lime' | 'teal'
export type BadgeSize = 'xs' | 'sm' | 'md' | 'lg'
export type BadgeStyle = 'filled' | 'outlined' | 'soft' | 'gradient' | 'glass' | 'dot'

export interface BadgeProps {
  children: React.ReactNode
  variant?: BadgeVariant
  size?: BadgeSize
  style?: BadgeStyle
  rounded?: 'sm' | 'md' | 'lg' | 'full'
  icon?: React.ReactNode
  dot?: boolean
  onRemove?: () => void
  className?: string
}

const styleVariantClasses = {
  filled: {
    primary: 'bg-brand-500 text-white dark:bg-brand-600',
    success: 'bg-green-500 text-white dark:bg-green-600',
    danger: 'bg-red-500 text-white dark:bg-red-600',
    warning: 'bg-yellow-500 text-white dark:bg-yellow-600',
    info: 'bg-blue-500 text-white dark:bg-blue-600',
    purple: 'bg-purple-500 text-white dark:bg-purple-600',
    gray: 'bg-gray-500 text-white dark:bg-gray-600',
    pink: 'bg-pink-500 text-white dark:bg-pink-600',
    indigo: 'bg-indigo-500 text-white dark:bg-indigo-600',
    cyan: 'bg-cyan-500 text-white dark:bg-cyan-600',
    lime: 'bg-lime-500 text-white dark:bg-lime-600',
    teal: 'bg-teal-500 text-white dark:bg-teal-600',
  },
  outlined: {
    primary: 'border-2 border-brand-500 text-brand-700 dark:text-brand-400 bg-transparent',
    success: 'border-2 border-green-500 text-green-700 dark:text-green-400 bg-transparent',
    danger: 'border-2 border-red-500 text-red-700 dark:text-red-400 bg-transparent',
    warning: 'border-2 border-yellow-500 text-yellow-700 dark:text-yellow-400 bg-transparent',
    info: 'border-2 border-blue-500 text-blue-700 dark:text-blue-400 bg-transparent',
    purple: 'border-2 border-purple-500 text-purple-700 dark:text-purple-400 bg-transparent',
    gray: 'border-2 border-gray-500 text-gray-700 dark:text-gray-400 bg-transparent',
    pink: 'border-2 border-pink-500 text-pink-700 dark:text-pink-400 bg-transparent',
    indigo: 'border-2 border-indigo-500 text-indigo-700 dark:text-indigo-400 bg-transparent',
    cyan: 'border-2 border-cyan-500 text-cyan-700 dark:text-cyan-400 bg-transparent',
    lime: 'border-2 border-lime-500 text-lime-700 dark:text-lime-400 bg-transparent',
    teal: 'border-2 border-teal-500 text-teal-700 dark:text-teal-400 bg-transparent',
  },
  soft: {
    primary: 'bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-400',
    success: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    danger: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    warning: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
    info: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    purple: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
    gray: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
    pink: 'bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-400',
    indigo: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
    cyan: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400',
    lime: 'bg-lime-100 text-lime-700 dark:bg-lime-900/30 dark:text-lime-400',
    teal: 'bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400',
  },
  gradient: {
    primary: 'bg-linear-to-r from-brand-500 to-red-500 text-white',
    success: 'bg-linear-to-r from-green-500 to-emerald-500 text-white',
    danger: 'bg-linear-to-r from-red-500 to-rose-500 text-white',
    warning: 'bg-linear-to-r from-yellow-500 to-brand-500 text-white',
    info: 'bg-linear-to-r from-blue-500 to-cyan-500 text-white',
    purple: 'bg-linear-to-r from-purple-500 to-pink-500 text-white',
    gray: 'bg-linear-to-r from-gray-500 to-slate-500 text-white',
    pink: 'bg-linear-to-r from-pink-500 to-rose-500 text-white',
    indigo: 'bg-linear-to-r from-indigo-500 to-purple-500 text-white',
    cyan: 'bg-linear-to-r from-cyan-500 to-blue-500 text-white',
    lime: 'bg-linear-to-r from-lime-500 to-green-500 text-white',
    teal: 'bg-linear-to-r from-teal-500 to-cyan-500 text-white',
  },
  glass: {
    primary: 'bg-brand-500/10 backdrop-blur-xs border border-brand-500/20 text-brand-700 dark:text-brand-400',
    success: 'bg-green-500/10 backdrop-blur-xs border border-green-500/20 text-green-700 dark:text-green-400',
    danger: 'bg-red-500/10 backdrop-blur-xs border border-red-500/20 text-red-700 dark:text-red-400',
    warning: 'bg-yellow-500/10 backdrop-blur-xs border border-yellow-500/20 text-yellow-700 dark:text-yellow-400',
    info: 'bg-blue-500/10 backdrop-blur-xs border border-blue-500/20 text-blue-700 dark:text-blue-400',
    purple: 'bg-purple-500/10 backdrop-blur-xs border border-purple-500/20 text-purple-700 dark:text-purple-400',
    gray: 'bg-gray-500/10 backdrop-blur-xs border border-gray-500/20 text-gray-700 dark:text-gray-400',
    pink: 'bg-pink-500/10 backdrop-blur-xs border border-pink-500/20 text-pink-700 dark:text-pink-400',
    indigo: 'bg-indigo-500/10 backdrop-blur-xs border border-indigo-500/20 text-indigo-700 dark:text-indigo-400',
    cyan: 'bg-cyan-500/10 backdrop-blur-xs border border-cyan-500/20 text-cyan-700 dark:text-cyan-400',
    lime: 'bg-lime-500/10 backdrop-blur-xs border border-lime-500/20 text-lime-700 dark:text-lime-400',
    teal: 'bg-teal-500/10 backdrop-blur-xs border border-teal-500/20 text-teal-700 dark:text-teal-400',
  },
  dot: {
    primary: 'bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-400',
    success: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    danger: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    warning: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
    info: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    purple: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
    gray: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
    pink: 'bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-400',
    indigo: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
    cyan: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400',
    lime: 'bg-lime-100 text-lime-700 dark:bg-lime-900/30 dark:text-lime-400',
    teal: 'bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400',
  },
}

const dotColorClasses = {
  primary: 'bg-brand-500',
  success: 'bg-green-500',
  danger: 'bg-red-500',
  warning: 'bg-yellow-500',
  info: 'bg-blue-500',
  purple: 'bg-purple-500',
  gray: 'bg-gray-500',
  pink: 'bg-pink-500',
  indigo: 'bg-indigo-500',
  cyan: 'bg-cyan-500',
  lime: 'bg-lime-500',
  teal: 'bg-teal-500',
}

const sizeClasses = {
  xs: 'px-1.5 py-0.5 text-xs gap-1',
  sm: 'px-2 py-0.5 text-xs gap-1.5',
  md: 'px-2.5 py-0.5 text-sm gap-1.5',
  lg: 'px-3 py-1 text-base gap-2',
}

const roundedClasses = {
  sm: 'rounded-xs',
  md: 'rounded-md',
  lg: 'rounded-lg',
  full: 'rounded-full',
}

export function Badge({
  children,
  variant = 'primary',
  size = 'md',
  style = 'soft',
  rounded = 'full',
  icon,
  dot = false,
  onRemove,
  className = '',
}: BadgeProps) {
  const colorClass = styleVariantClasses[style][variant]
  const sizeClass = sizeClasses[size]
  const roundedClass = roundedClasses[rounded]

  return (
    <span
      className={`inline-flex items-center justify-center whitespace-nowrap font-medium transition-all ${roundedClass} ${sizeClass} ${colorClass} ${className}`}
    >
      {dot && (
        <span className={`size-2 rounded-full ${dotColorClasses[variant]} mr-1.5 shrink-0`} />
      )}
      
      {icon && <span className="shrink-0">{icon}</span>}
      
      <span>{children}</span>

      {onRemove && (
        <button
          onClick={onRemove}
          className="shrink-0 ml-1 rounded-full p-0.5 hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
          aria-label="Remover"
        >
          <X className="size-3" />
        </button>
      )}
    </span>
  )
}

// Badges preconfigurados para estados comunes
export function StatusBadge({ status }: { status: 'active' | 'inactive' | 'pending' | 'completed' | 'cancelled' }) {
  const config = {
    active: { variant: 'success' as BadgeVariant, label: 'Activo' },
    inactive: { variant: 'gray' as BadgeVariant, label: 'Inactivo' },
    pending: { variant: 'warning' as BadgeVariant, label: 'Pendiente' },
    completed: { variant: 'success' as BadgeVariant, label: 'Completado' },
    cancelled: { variant: 'danger' as BadgeVariant, label: 'Cancelado' },
  }

  const { variant, label } = config[status]

  return <Badge variant={variant}>{label}</Badge>
}

export function PaymentBadge({ status }: { status: 'paid' | 'unpaid' | 'partial' | 'overdue' }) {
  const config = {
    paid: { variant: 'success' as BadgeVariant, label: 'Pagado' },
    unpaid: { variant: 'danger' as BadgeVariant, label: 'No Pagado' },
    partial: { variant: 'warning' as BadgeVariant, label: 'Pago Parcial' },
    overdue: { variant: 'danger' as BadgeVariant, label: 'Vencido' },
  }

  const { variant, label } = config[status]

  return <Badge variant={variant}>{label}</Badge>
}

export function StockBadge({ level }: { level: 'in-stock' | 'low-stock' | 'out-of-stock' }) {
  const config = {
    'in-stock': { variant: 'success' as BadgeVariant, label: 'En Stock' },
    'low-stock': { variant: 'warning' as BadgeVariant, label: 'Stock Bajo' },
    'out-of-stock': { variant: 'danger' as BadgeVariant, label: 'Sin Stock' },
  }

  const { variant, label} = config[level]

  return <Badge variant={variant}>{label}</Badge>
}
