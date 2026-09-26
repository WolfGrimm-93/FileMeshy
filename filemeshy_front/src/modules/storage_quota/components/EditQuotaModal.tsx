/**
 * Modal de edición de cuota de almacenamiento de un usuario.
 *
 * Decisión de implementación: el input pide el límite en GB (más legible para
 * un admin que tipear bytes crudos) y se convierte a bytes al guardar. Dejar
 * el campo vacío equivale a "sin límite" (limit_bytes: null), tal como pide
 * el contrato del backend.
 */
import { useState } from 'react'
import { Loader2, Save } from 'lucide-react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'
import { Input } from '@/ui/inputs/Input'
import type { StorageQuotaItem } from '../services/storage-quota.service'

const GB = 1024 * 1024 * 1024

interface EditQuotaModalProps {
  isOpen: boolean
  onClose: () => void
  quota: StorageQuotaItem | null
  onSave: (userId: string, limitBytes: number | null) => Promise<void>
}

/**
 * Mount-gate: no monta nada si no hay cuota o está cerrado, y el interior se remonta por
 * `user_id`, así cada apertura precarga el límite actual (en GB) sin efectos de sincronización.
 */
export function EditQuotaModal({ isOpen, onClose, quota, onSave }: EditQuotaModalProps) {
  if (!quota || !isOpen) return null
  return <EditQuotaModalInner key={quota.user_id} onClose={onClose} quota={quota} onSave={onSave} />
}

interface EditQuotaModalInnerProps {
  onClose: () => void
  quota: StorageQuotaItem
  onSave: (userId: string, limitBytes: number | null) => Promise<void>
}

function EditQuotaModalInner({ onClose, quota, onSave }: EditQuotaModalInnerProps) {
  const [limitGb, setLimitGb] = useState(() =>
    quota.limit_bytes === null ? '' : String(quota.limit_bytes / GB),
  )
  const [isSaving, setIsSaving] = useState(false)

  const handleSave = async () => {
    const trimmed = limitGb.trim()
    const limitBytes = trimmed === '' ? null : Math.round(parseFloat(trimmed) * GB)

    if (limitBytes !== null && (isNaN(limitBytes) || limitBytes <= 0)) {
      return
    }

    setIsSaving(true)
    try {
      await onSave(quota.user_id, limitBytes)
      onClose()
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <Modal
      isOpen
      onClose={onClose}
      title="Editar cuota de almacenamiento"
      size="sm"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={isSaving}>
            Cancelar
          </Button>
          <Button
            variant="primary"
            leftIcon={isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            onClick={handleSave}
            disabled={isSaving}
          >
            Guardar
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">
          {quota.first_name} {quota.last_name} — {quota.email}
        </p>

        <Input
          label="Límite de almacenamiento (GB)"
          type="number"
          min={0}
          step="0.1"
          value={limitGb}
          onChange={(e) => setLimitGb(e.target.value)}
          placeholder="Dejar vacío para sin límite"
          helperText="Dejá el campo vacío para no aplicar límite a este usuario"
          fullWidth
        />
      </div>
    </Modal>
  )
}
