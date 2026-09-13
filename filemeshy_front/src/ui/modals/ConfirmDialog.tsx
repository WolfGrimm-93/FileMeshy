import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'
import { Modal } from './Modal'

export interface ConfirmDialogProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  message: string
  variant?: 'danger' | 'warning' | 'info' | 'success'
  confirmText?: string
  cancelText?: string
  showIcon?: boolean
}

const variantConfig = {
  danger: {
    icon: <XCircle className="size-12" />,
    iconBgClass: 'bg-red-100 dark:bg-red-900/20',
    iconTextClass: 'text-red-600 dark:text-red-400',
    buttonClass: 'bg-red-600 hover:bg-red-700 text-white',
  },
  warning: {
    icon: <AlertTriangle className="size-12" />,
    iconBgClass: 'bg-yellow-100 dark:bg-yellow-900/20',
    iconTextClass: 'text-yellow-600 dark:text-yellow-400',
    buttonClass: 'bg-yellow-600 hover:bg-yellow-700 text-white',
  },
  info: {
    icon: <Info className="size-12" />,
    iconBgClass: 'bg-blue-100 dark:bg-blue-900/20',
    iconTextClass: 'text-blue-600 dark:text-blue-400',
    buttonClass: 'bg-blue-600 hover:bg-blue-700 text-white',
  },
  success: {
    icon: <CheckCircle2 className="size-12" />,
    iconBgClass: 'bg-green-100 dark:bg-green-900/20',
    iconTextClass: 'text-green-600 dark:text-green-400',
    buttonClass: 'bg-green-600 hover:bg-green-700 text-white',
  },
}

export function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  variant = 'warning',
  confirmText = 'Confirmar',
  cancelText = 'Cancelar',
  showIcon = true,
}: ConfirmDialogProps) {
  const config = variantConfig[variant]

  const handleConfirm = () => {
    onConfirm()
    onClose()
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title=""
      size="sm"
      showCloseButton={false}
      closeOnOverlayClick={false}
    >
      <div className="text-center">
        {showIcon && (
          <div className="mx-auto mb-4 flex items-center justify-center">
            <div className={`rounded-full p-3 ${config.iconBgClass} ${config.iconTextClass}`}>
              {config.icon}
            </div>
          </div>
        )}

        <h3 className="mb-2 text-xl font-semibold text-gray-900 dark:text-white">
          {title}
        </h3>

        <p className="mb-6 text-gray-600 dark:text-gray-400">
          {message}
        </p>

        <div className="flex gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-hidden focus:ring-2 focus:ring-gray-200 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700 dark:focus:ring-gray-700"
          >
            {cancelText}
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className={`flex-1 rounded-lg px-4 py-2.5 text-sm font-medium focus:outline-hidden focus:ring-2 focus:ring-offset-2 ${config.buttonClass}`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </Modal>
  )
}
