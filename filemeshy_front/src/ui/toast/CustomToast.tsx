/**
 * Sistema de Toast personalizable con múltiples estilos
 * Compatible con el sistema de temas de la aplicación
 */
import { toast as sonnerToast } from 'sonner'
import { CheckCircle2, AlertCircle, AlertTriangle, Info, X, Loader2 } from 'lucide-react'
import { type ReactNode } from 'react'

export type ToastVariant = 'success' | 'error' | 'warning' | 'info' | 'loading'
export type ToastStyle = 'glassmorphism' | 'solid' | 'minimal' | 'bordered' | 'gradient'

interface ToastConfig {
  icon: React.ReactNode
  bgClass: string
  textClass: string
  iconClass: string
  borderClass: string
  gradientClass: string
}

const variantConfig: Record<ToastVariant, ToastConfig> = {
  success: {
    icon: <CheckCircle2 className="size-5" />,
    bgClass: 'bg-white/15 dark:bg-white/10',
    textClass: 'text-green-700 dark:text-green-400',
    iconClass: 'text-green-600 dark:text-green-500',
    borderClass: 'border-green-500/50 dark:border-green-400/50',
    gradientClass: 'bg-linear-to-r from-green-500/10 to-emerald-500/10 dark:from-green-500/20 dark:to-emerald-500/20',
  },
  error: {
    icon: <AlertCircle className="size-5" />,
    bgClass: 'bg-white/15 dark:bg-white/10',
    textClass: 'text-red-700 dark:text-red-400',
    iconClass: 'text-red-600 dark:text-red-500',
    borderClass: 'border-red-500/50 dark:border-red-400/50',
    gradientClass: 'bg-linear-to-r from-red-500/10 to-rose-500/10 dark:from-red-500/20 dark:to-rose-500/20',
  },
  warning: {
    icon: <AlertTriangle className="size-5" />,
    bgClass: 'bg-white/15 dark:bg-white/10',
    textClass: 'text-yellow-700 dark:text-yellow-400',
    iconClass: 'text-yellow-600 dark:text-yellow-500',
    borderClass: 'border-yellow-500/50 dark:border-yellow-400/50',
    gradientClass: 'bg-linear-to-r from-yellow-500/10 to-amber-500/10 dark:from-yellow-500/20 dark:to-amber-500/20',
  },
  info: {
    icon: <Info className="size-5" />,
    bgClass: 'bg-white/15 dark:bg-white/10',
    textClass: 'text-blue-700 dark:text-blue-400',
    iconClass: 'text-blue-600 dark:text-blue-500',
    borderClass: 'border-blue-500/50 dark:border-blue-400/50',
    gradientClass: 'bg-linear-to-r from-blue-500/10 to-cyan-500/10 dark:from-blue-500/20 dark:to-cyan-500/20',
  },
  loading: {
    icon: <Loader2 className="size-5 animate-spin" />,
    bgClass: 'bg-white/15 dark:bg-white/10',
    textClass: 'text-gray-700 dark:text-gray-400',
    iconClass: 'text-gray-600 dark:text-gray-500',
    borderClass: 'border-gray-500/50 dark:border-gray-400/50',
    gradientClass: 'bg-linear-to-r from-gray-500/10 to-slate-500/10 dark:from-gray-500/20 dark:to-slate-500/20',
  },
}

interface CustomToastOptions {
  id?: string | number
  variant?: ToastVariant
  duration?: number
  position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'top-center' | 'bottom-center'
  style?: ToastStyle
  title?: string
  description?: string
  icon?: ReactNode
  closable?: boolean
  className?: string
  onClose?: () => void
  /** Botón de acción opcional (ej: "Emitir Nota de Crédito"). Al pulsarlo cierra el toast. */
  action?: { label: string; onClick: () => void }
}

/**
 * Obtiene las clases CSS según el estilo seleccionado
 */
function getStyleClasses(style: ToastStyle, config: ToastConfig): string {
  const baseClasses = 'rounded-lg p-4 min-w-[260px] max-w-[calc(100vw-2rem)] sm:min-w-[320px] sm:max-w-[420px] flex items-start gap-3 animate-in slide-in-from-top-2'
  
  const styleMap: Record<ToastStyle, string> = {
    glassmorphism: `${config.bgClass} backdrop-blur-[10px] border border-white/18 shadow-[0_8px_32px_0_rgba(31,38,135,0.37)]`,
    solid: `bg-white dark:bg-gray-800 border ${config.borderClass} shadow-lg`,
    minimal: `bg-transparent border-l-4 ${config.borderClass} pl-4`,
    bordered: `bg-white dark:bg-gray-800 border-2 ${config.borderClass} shadow-md`,
    gradient: `${config.gradientClass} backdrop-blur-xs border ${config.borderClass} shadow-lg`,
  }

  return `${baseClasses} ${styleMap[style]}`
}

/**
 * Muestra un toast personalizado
 */
export function showToast(
  message: string,
  options: CustomToastOptions = {}
) {
  const {
    id,
    variant = 'info',
    duration = 3000,
    position = 'top-right',
    style = 'glassmorphism',
    title,
    description,
    icon,
    closable = false,
    className = '',
    onClose,
    action,
  } = options

  const config = variantConfig[variant]
  const displayIcon = icon || config.icon
  const styleClasses = getStyleClasses(style, config)

  return sonnerToast.custom(
    (t) => (
      <div className={`${styleClasses} ${className}`}>
        <span className={`${config.iconClass} mt-0.5 shrink-0`}>
          {displayIcon}
        </span>
        
        <div className="flex-1 min-w-0">
          {title && (
            <p className={`${config.textClass} text-sm font-semibold mb-1`}>
              {title}
            </p>
          )}
          <p className={`${config.textClass} text-sm ${title ? 'font-normal' : 'font-medium'} leading-tight`}>
            {message}
          </p>
          {description && (
            <p className={`${config.textClass} text-xs opacity-80 mt-1`}>
              {description}
            </p>
          )}
          {action && (
            <button
              onClick={() => {
                sonnerToast.dismiss(t)
                action.onClick()
              }}
              className={`mt-2 inline-flex items-center rounded-md border ${config.borderClass} ${config.textClass} px-3 py-1 text-xs font-semibold hover:opacity-80 transition-opacity`}
            >
              {action.label}
            </button>
          )}
        </div>

        {closable && (
          <button
            onClick={() => {
              sonnerToast.dismiss(t)
              onClose?.()
            }}
            className={`${config.iconClass} hover:opacity-70 transition-opacity shrink-0`}
            aria-label="Cerrar"
          >
            <X className="size-4" />
          </button>
        )}
      </div>
    ),
    {
      id,
      duration: variant === 'loading' ? Infinity : duration,
      position,
    }
  )
}

/**
 * API principal del toast con métodos helper
 */
export const toast = {
  // Método base
  show: showToast,

  // Variantes básicas
  success: (message: string, options?: Omit<CustomToastOptions, 'variant'>) =>
    showToast(message, { ...options, variant: 'success' }),

  error: (message: string, options?: Omit<CustomToastOptions, 'variant'>) =>
    showToast(message, { ...options, variant: 'error' }),

  warning: (message: string, options?: Omit<CustomToastOptions, 'variant'>) =>
    showToast(message, { ...options, variant: 'warning' }),

  info: (message: string, options?: Omit<CustomToastOptions, 'variant'>) =>
    showToast(message, { ...options, variant: 'info' }),

  loading: (message: string, options?: Omit<CustomToastOptions, 'variant'>) =>
    showToast(message, { ...options, variant: 'loading' }),

  // Estilos específicos
  glassmorphism: (message: string, variant?: ToastVariant, options?: CustomToastOptions) =>
    showToast(message, { ...options, variant, style: 'glassmorphism' }),

  solid: (message: string, variant?: ToastVariant, options?: CustomToastOptions) =>
    showToast(message, { ...options, variant, style: 'solid' }),

  minimal: (message: string, variant?: ToastVariant, options?: CustomToastOptions) =>
    showToast(message, { ...options, variant, style: 'minimal' }),

  bordered: (message: string, variant?: ToastVariant, options?: CustomToastOptions) =>
    showToast(message, { ...options, variant, style: 'bordered' }),

  gradient: (message: string, variant?: ToastVariant, options?: CustomToastOptions) =>
    showToast(message, { ...options, variant, style: 'gradient' }),

  // Utilidades
  dismiss: (toastId?: string | number) => sonnerToast.dismiss(toastId),
  
  promise: <T,>(
    promise: Promise<T>,
    options: {
      loading: string
      success: string | ((data: T) => string)
      error: string | ((error: Error) => string)
      style?: ToastStyle
    }
  ) => {
    const { loading, success, error, style: _style = 'glassmorphism' } = options
    
    return sonnerToast.promise(promise, {
      loading,
      success,
      error,
    })
  },
}
