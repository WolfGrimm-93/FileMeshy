/**
 * Diálogo de confirmación para eliminación
 */
import { ConfirmDialog } from '@/ui/modals/ConfirmDialog'

interface DeleteConfirmDialogProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  description: string
}

export default function DeleteConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  description
}: DeleteConfirmDialogProps) {
  return (
    <ConfirmDialog
      isOpen={isOpen}
      onClose={onClose}
      onConfirm={onConfirm}
      title={title}
      message={description}
      variant="danger"
      confirmText="Eliminar"
      cancelText="Cancelar"
    />
  )
}
