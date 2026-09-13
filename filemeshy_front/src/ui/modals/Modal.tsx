import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'

export interface ModalProps {
  isOpen: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl' | '4xl'
  showCloseButton?: boolean
  closeOnOverlayClick?: boolean
  footer?: React.ReactNode
  className?: string
}

const sizeClasses = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
  '3xl': 'max-w-3xl',
  '4xl': 'max-w-4xl',
}

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  size = 'md',
  showCloseButton = true,
  closeOnOverlayClick = true,
  footer,
  className = '',
}: ModalProps) {
  // Cerrar con tecla Escape
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose()
      }
    }

    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [isOpen, onClose])

  // Prevenir scroll del body cuando el modal está abierto
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = 'unset'
    }

    return () => {
      document.body.style.overflow = 'unset'
    }
  }, [isOpen])

  if (!isOpen) return null

  return createPortal(
    <>
      {/* Backdrop — renderizado en document.body, fuera de cualquier overflow */}
      <div
        className="fixed inset-0 z-50 bg-black/50"
        onClick={closeOnOverlayClick ? onClose : undefined}
      />

      {/* Contenedor de centrado */}
      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modalTitle"
        onClick={closeOnOverlayClick ? onClose : undefined}
      >
        <div
          className={`w-full ${sizeClasses[size]} max-h-[90vh] flex flex-col rounded-lg bg-white shadow-lg dark:bg-gray-900 ${className}`}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header fijo */}
          <div className="flex items-start justify-between p-6 pb-0 shrink-0">
            <h2
              id="modalTitle"
              className="text-xl font-bold text-gray-900 dark:text-white sm:text-2xl"
            >
              {title}
            </h2>

            {showCloseButton && (
              <button
                type="button"
                onClick={onClose}
                className="-me-4 -mt-4 rounded-full p-2 text-gray-400 transition-colors hover:bg-gray-50 hover:text-gray-600 focus:outline-hidden dark:hover:bg-gray-800 dark:hover:text-gray-300"
                aria-label="Cerrar"
              >
                <X className="size-5" />
              </button>
            )}
          </div>

          {/* Cuerpo con scroll si el contenido es largo */}
          <div className="overflow-y-auto p-6 pt-4 text-pretty text-gray-700 dark:text-gray-300">
            {children}
          </div>

          {footer && <footer className="p-6 pt-0 shrink-0">{footer}</footer>}
        </div>
      </div>
    </>,
    document.body
  )
}

// Modal de confirmación
export interface ConfirmModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  variant?: 'danger' | 'warning' | 'info'
}

export function ConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmText = 'Confirmar',
  cancelText = 'Cancelar',
  variant = 'danger',
}: ConfirmModalProps) {
  const confirmButtonClasses = {
    danger: 'bg-red-600 hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-800',
    warning: 'bg-yellow-600 hover:bg-yellow-700 dark:bg-yellow-700 dark:hover:bg-yellow-800',
    info: 'bg-blue-600 hover:bg-blue-700 dark:bg-blue-700 dark:hover:bg-blue-800',
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      size="sm"
      footer={
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
          >
            {cancelText}
          </button>
          <button
            type="button"
            onClick={() => {
              onConfirm()
              onClose()
            }}
            className={`rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors ${confirmButtonClasses[variant]}`}
          >
            {confirmText}
          </button>
        </div>
      }
    >
      {message}
    </Modal>
  )
}

// Modal de eliminación
export function DeleteModal({
  isOpen,
  onClose,
  onConfirm,
  itemName,
}: {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  itemName: string
}) {
  return (
    <ConfirmModal
      isOpen={isOpen}
      onClose={onClose}
      onConfirm={onConfirm}
      title="Confirmar Eliminación"
      message={`¿Estás seguro de que deseas eliminar "${itemName}"? Esta acción no se puede deshacer.`}
      confirmText="Eliminar"
      cancelText="Cancelar"
      variant="danger"
    />
  )
}
