import { CheckCircle2, AlertCircle, AlertTriangle, Info, X } from 'lucide-react';

export type AlertVariant = 'success' | 'error' | 'warning' | 'info'

export interface AlertProps {
  variant: AlertVariant
  title?: string
  message: string
  onClose?: () => void
  className?: string
}

const variantConfig = {
  success: {
    border: 'border-green-500 dark:border-green-700',
    bg: 'bg-green-50 dark:bg-green-900/20',
    titleColor: 'text-green-800 dark:text-green-300',
    messageColor: 'text-green-700 dark:text-green-400',
    iconColor: 'text-green-700 dark:text-green-500',
    icon: <CheckCircle2 className="size-6" />,
  },
  error: {
    border: 'border-red-500 dark:border-red-700',
    bg: 'bg-red-50 dark:bg-red-900/20',
    titleColor: 'text-red-800 dark:text-red-300',
    messageColor: 'text-red-700 dark:text-red-400',
    iconColor: 'text-red-700 dark:text-red-500',
    icon: <AlertCircle className="size-6" />,
  },
  warning: {
    border: 'border-yellow-500 dark:border-yellow-700',
    bg: 'bg-yellow-50 dark:bg-yellow-900/20',
    titleColor: 'text-yellow-800 dark:text-yellow-300',
    messageColor: 'text-yellow-700 dark:text-yellow-400',
    iconColor: 'text-yellow-700 dark:text-yellow-500',
    icon: <AlertTriangle className="size-6" />,
  },
  info: {
    border: 'border-blue-500 dark:border-blue-700',
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    titleColor: 'text-blue-800 dark:text-blue-300',
    messageColor: 'text-blue-700 dark:text-blue-400',
    iconColor: 'text-blue-700 dark:text-blue-500',
    icon: <Info className="size-6" />,
  },
}

export function Alert({ variant, title, message, onClose, className = '' }: AlertProps) {
  const config = variantConfig[variant]
  const defaultTitles = {
    success: 'Éxito',
    error: 'Error',
    warning: 'Advertencia',
    info: 'Información',
  }

  return (
    <div
      role="alert"
      className={`rounded-md border p-4 shadow-xs ${config.border} ${config.bg} ${className}`}
    >
      <div className="flex items-start gap-4">
        <span className={`-mt-0.5 ${config.iconColor}`}>{config.icon}</span>

        <div className="flex-1">
          <strong className={`block font-medium leading-tight ${config.titleColor}`}>
            {title || defaultTitles[variant]}
          </strong>

          <p className={`mt-0.5 text-sm ${config.messageColor}`}>{message}</p>
        </div>

        {onClose && (
          <button
            onClick={onClose}
            className={`-mt-0.5 transition hover:opacity-75 ${config.iconColor}`}
            aria-label="Cerrar"
          >
            <X className="size-5" />
          </button>
        )}
      </div>
    </div>
  )
}

// Shortcuts para alertas específicas
export function SuccessAlert({ title = 'Éxito', message, onClose, className }: Omit<AlertProps, 'variant'>) {
  return <Alert variant="success" title={title} message={message} onClose={onClose} className={className} />
}

export function ErrorAlert({ title = 'Error', message, onClose, className }: Omit<AlertProps, 'variant'>) {
  return <Alert variant="error" title={title} message={message} onClose={onClose} className={className} />
}

export function WarningAlert({ title = 'Advertencia', message, onClose, className }: Omit<AlertProps, 'variant'>) {
  return <Alert variant="warning" title={title} message={message} onClose={onClose} className={className} />
}

export function InfoAlert({ title = 'Información', message, onClose, className }: Omit<AlertProps, 'variant'>) {
  return <Alert variant="info" title={title} message={message} onClose={onClose} className={className} />
}
