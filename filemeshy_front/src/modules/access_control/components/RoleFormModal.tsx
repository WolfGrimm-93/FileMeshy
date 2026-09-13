/**
 * Modal para crear/editar roles
 */
import { useState, useEffect } from 'react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'
import { Input } from '@/ui/inputs/Input'
import { Textarea } from '@/ui/inputs/Textarea'
import { Switch } from '@/ui/inputs/Switch'
import { toast } from 'sonner'
import { rolesService } from '../services/roles.service'
import type { RoleResponse, RoleCreate, RoleUpdate } from '../types/role.types'
import RolePermissionsEditor from './RolePermissionsEditor.tsx'

interface RoleFormModalProps {
  role?: RoleResponse
  onClose: () => void
  onSave: () => void
}

export default function RoleFormModal({ role, onClose, onSave }: RoleFormModalProps) {
  const isEdit = !!role
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Form state
  const [name, setName] = useState(role?.name || '')
  const [displayName, setDisplayName] = useState(role?.display_name || '')
  const [description, setDescription] = useState(role?.description || '')
  const [isActive, setIsActive] = useState(role?.is_active ?? true)
  const [permissions, setPermissions] = useState(role?.permissions || {})

  // Validation
  const [nameError, setNameError] = useState('')

  // Validar nombre cuando cambia
  useEffect(() => {
    if (!name) {
      setNameError('')
      return
    }

    const validation = rolesService.validateRoleName(name)
    setNameError(validation.valid ? '' : validation.error || '')
  }, [name])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    // Validaciones
    if (!name.trim()) {
      toast.error('El nombre es requerido')
      return
    }

    if (!displayName.trim()) {
      toast.error('El nombre para mostrar es requerido')
      return
    }

    if (nameError) {
      toast.error(nameError)
      return
    }

    try {
      setIsSubmitting(true)

      if (isEdit && role) {
        // Actualizar
        const updateData: RoleUpdate = {
          display_name: displayName,
          description: description || undefined,
          permissions,
          is_active: isActive
        }
        await rolesService.update(role.id, updateData)
        toast.success('Rol actualizado correctamente')
      } else {
        // Crear
        const createData: RoleCreate = {
          name: name.toUpperCase(),
          display_name: displayName,
          description: description || undefined,
          permissions,
          is_active: isActive
        }
        await rolesService.create(createData)
        toast.success('Rol creado correctamente')
      }

      onSave()
    } catch (error: unknown) {
      console.error('Error al guardar rol:', error)
      const message = error instanceof Error ? error.message : 'Error al guardar rol'
      toast.error(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={isEdit ? 'Editar Rol' : 'Crear Nuevo Rol'}
      size="3xl"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={isSubmitting}>
            Cancelar
          </Button>
          <Button onClick={handleSubmit} disabled={isSubmitting || !!nameError}>
            {isSubmitting ? 'Guardando...' : isEdit ? 'Actualizar' : 'Crear'}
          </Button>
        </div>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Información básica */}
        <div className="space-y-4">
          <div>
            <Input
              label="Nombre del rol"
              value={name}
              onChange={(e) => setName(e.target.value.toUpperCase())}
              placeholder="AUDITOR"
              required
              disabled={isEdit} // No se puede cambiar el nombre en edición
              error={nameError}
              helperText={
                isEdit
                  ? 'El nombre no puede ser modificado'
                  : 'Solo letras mayúsculas y guiones bajos. Ej: AUDITOR, SOPORTE_TECNICO'
              }
            />
          </div>

          <div>
            <Input
              label="Nombre para mostrar"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Vendedor"
              required
              helperText="Nombre legible que se mostrará en la interfaz"
            />
          </div>

          <div>
            <Textarea
              label="Descripción"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Descripción del rol y sus responsabilidades"
              rows={3}
            />
          </div>

          <div>
            <Switch
              label="Rol activo"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
            />
          </div>
        </div>

        {/* Editor de permisos */}
        <div className="border-t pt-6">
          <h3 className="text-lg font-semibold mb-4">Permisos</h3>
          <RolePermissionsEditor
            permissions={permissions}
            onChange={setPermissions}
          />
        </div>
      </form>
    </Modal>
  )
}
