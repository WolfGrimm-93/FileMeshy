/**
 * PÁGINA: CREAR ROL
 * Formulario para crear un nuevo rol
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Save, Shield } from 'lucide-react'
import { Button } from '../../../ui/buttons/Button'
import { Input } from '../../../ui/inputs/Input'
import { Textarea } from '../../../ui/inputs/Textarea'
import { Switch } from '../../../ui/inputs/Switch'
import { toast } from 'sonner'
import { rolesService } from '../services/roles.service'
import { permissionsAssignmentService, permissionsDictToIds } from '../services/permissions-assignment.service'
import type { RoleCreate, RolePermissions } from '../types/role.types'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import RolePermissionsEditor from '../components/RolePermissionsEditor'

export default function RoleCreatePage() {
  const navigate = useNavigate()
  const { user: authUser } = useAuth()

  const [isSubmitting, setIsSubmitting] = useState(false)

  // Form state
  const [name, setName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [description, setDescription] = useState('')
  const [isActive, setIsActive] = useState(true)
  const [permissions, setPermissions] = useState<RolePermissions>({})

  // Validation
  const [nameError, setNameError] = useState('')

  const isSuperAdmin = authUser?.role === 'SUPER_ADMIN'

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

    if (!isSuperAdmin) {
      toast.error('Solo SUPER_ADMIN puede crear roles')
      return
    }

    try {
      setIsSubmitting(true)

      const createData: RoleCreate = {
        name: name.toUpperCase(),
        display_name: displayName,
        description: description || undefined,
        // Role.permissions (JSONB) no tiene ningún lector real en el backend --
        // se manda igual porque el schema lo pide, pero el efecto real viene del
        // PUT de abajo, contra la tabla role_permissions.
        permissions,
        is_active: isActive
      }

      const newRole = await rolesService.create(createData)

      // Asignar de verdad los permisos marcados en el checklist. El POST de
      // arriba NO los aplica (bug real encontrado 2026-08-26: guardaba en
      // Role.permissions, el JSONB legacy sin efecto -- el rol nuevo quedaba
      // con 0 permisos reales hasta entrar aparte a "Gestión de Permisos").
      // Se resuelve el permission_id real de cada elección contra el catálogo
      // (que este endpoint ya devuelve) y se aplica con el mismo PUT que usa
      // PermissionsManagementPage.
      const permIds = permissionsDictToIds(
        permissions,
        (await permissionsAssignmentService.getForRole(newRole.id)).catalog
      )
      if (permIds.length > 0) {
        await permissionsAssignmentService.updateForRole(newRole.id, permIds)
      }

      toast.success('Rol creado correctamente')
      navigate(`/roles/${newRole.id}`)
    } catch (error: unknown) {
      console.error('Error al crear rol:', error)
      const message = error instanceof Error ? error.message : 'Error al crear rol'
      toast.error(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="w-full">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className="size-4" />} onClick={() => navigate('/roles')}>
            Volver
          </Button>
          <div className="w-px h-8 bg-border" />
          <div className="w-12 h-12 bg-linear-to-br from-brand-400 to-brand-600 rounded-xl flex items-center justify-center">
            <Shield className="text-white" size={24} />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-foreground">Crear Nuevo Rol</h1>
            <p className="text-muted-foreground">
              Define un nuevo rol con permisos personalizados
            </p>
          </div>
        </div>
      </div>

      {/* Formulario */}
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Información Básica */}
        <div className="bg-muted rounded-xl shadow-xs border border-border p-6">
          <h2 className="text-lg font-semibold text-foreground mb-4">
            Información Básica
          </h2>
          <div className="space-y-4">
            <div>
              <Input
                label="Nombre del rol *"
                value={name}
                onChange={(e) => setName(e.target.value.toUpperCase())}
                placeholder="AUDITOR"
                required
                error={nameError}
                helperText="Solo letras mayúsculas y guiones bajos. Ej: AUDITOR, SOPORTE_TECNICO"
              />
            </div>

            <div>
              <Input
                label="Nombre para mostrar *"
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
        </div>

        {/* Permisos */}
        <div className="bg-muted rounded-xl shadow-xs border border-border p-6">
          <h2 className="text-lg font-semibold text-foreground mb-4">Permisos</h2>
          <RolePermissionsEditor permissions={permissions} onChange={setPermissions} />
        </div>

        {/* Botones */}
        <div className="flex items-center justify-end gap-3">
          <Button
            type="button"
            variant="secondary"
            onClick={() => navigate('/roles')}
            disabled={isSubmitting}
          >
            Cancelar
          </Button>
          <Button
            type="submit"
            variant="primary"
            leftIcon={<Save size={18} />}
            isLoading={isSubmitting}
            disabled={!!nameError}
          >
            Crear Rol
          </Button>
        </div>
      </form>
    </div>
  )
}
