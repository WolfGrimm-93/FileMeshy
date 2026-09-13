import { useState } from 'react'
import { FolderPlus } from 'lucide-react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'
import { Input } from '@/ui/inputs/Input'
import { toast } from '@/ui/toast/CustomToast'
import { extractErrorMessage } from '@/shared/utils/errors'
import { foldersService } from '../services/folders.service'
import type { FolderOut } from '../types'

interface CreateFolderModalProps {
  isOpen: boolean
  onClose: () => void
  parentId: string | null
  onCreated: (folder: FolderOut) => void
}

export default function CreateFolderModal({ isOpen, onClose, parentId, onCreated }: CreateFolderModalProps) {
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)

  const handleClose = () => {
    if (saving) return
    setName('')
    onClose()
  }

  const handleSubmit = async () => {
    const trimmed = name.trim()
    if (!trimmed) {
      toast.error('El nombre de la carpeta es obligatorio')
      return
    }

    setSaving(true)
    try {
      const folder = await foldersService.create(trimmed, parentId)
      toast.success('Carpeta creada correctamente')
      onCreated(folder)
      setName('')
      onClose()
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al crear la carpeta'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Nueva carpeta"
      size="sm"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={handleClose} disabled={saving}>
            Cancelar
          </Button>
          <Button
            variant="primary"
            leftIcon={<FolderPlus className="size-4" />}
            onClick={handleSubmit}
            isLoading={saving}
            loadingText="Creando..."
          >
            Crear carpeta
          </Button>
        </div>
      }
    >
      <Input
        label="Nombre de la carpeta"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Ej. Contratos 2026"
        autoFocus
        onKeyDown={(e) => {
          if (e.key === 'Enter') handleSubmit()
        }}
      />
    </Modal>
  )
}
