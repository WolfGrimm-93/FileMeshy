import { useEffect, useState } from 'react'
import { Check } from 'lucide-react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'
import { Input } from '@/ui/inputs/Input'
import { toast } from '@/ui/toast/CustomToast'
import { extractErrorMessage } from '@/shared/utils/errors'
import { foldersService } from '../services/folders.service'
import { filesService } from '../services/files.service'

export interface RenameTarget {
  id: string
  name: string
  type: 'folder' | 'file'
}

interface RenameModalProps {
  target: RenameTarget | null
  onClose: () => void
  onRenamed: (target: RenameTarget, newName: string) => void
}

export default function RenameModal({ target, onClose, onRenamed }: RenameModalProps) {
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setName(target?.name ?? '')
  }, [target])

  const handleClose = () => {
    if (saving) return
    onClose()
  }

  const handleSubmit = async () => {
    if (!target) return
    const trimmed = name.trim()
    if (!trimmed) {
      toast.error('El nombre no puede estar vacío')
      return
    }

    setSaving(true)
    try {
      if (target.type === 'folder') {
        await foldersService.rename(target.id, trimmed)
      } else {
        await filesService.rename(target.id, trimmed)
      }
      toast.success('Nombre actualizado correctamente')
      onRenamed(target, trimmed)
      onClose()
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al renombrar'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      isOpen={!!target}
      onClose={handleClose}
      title={target?.type === 'folder' ? 'Renombrar carpeta' : 'Renombrar archivo'}
      size="sm"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={handleClose} disabled={saving}>
            Cancelar
          </Button>
          <Button
            variant="primary"
            leftIcon={<Check className="size-4" />}
            onClick={handleSubmit}
            isLoading={saving}
            loadingText="Guardando..."
          >
            Guardar
          </Button>
        </div>
      }
    >
      <Input
        label="Nuevo nombre"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
        onKeyDown={(e) => {
          if (e.key === 'Enter') handleSubmit()
        }}
      />
    </Modal>
  )
}
