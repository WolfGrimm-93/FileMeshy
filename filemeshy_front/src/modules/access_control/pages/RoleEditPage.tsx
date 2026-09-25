/**
 * PÁGINA: EDITAR ROL
 * Formulario para editar un rol existente
 */

import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Save, Shield } from 'lucide-react'
import { Button } from '../../../ui/buttons/Button'
import { Input } from '../../../ui/inputs/Input'
import { Textarea } from '../../../ui/inputs/Textarea'
import { Switch } from '../../../ui/inputs/Switch'
import { toast } from 'sonner'
import { rolesService } from '../services/roles.service'
import {
  permissionsAssignmentService,
  idsToPermissionsDict,
  permissionsDictToIds,
  type PermissionCatalogItem,
} from '../services/permissions-assignment.service'
import type { RoleResponse, RoleUpdate, RolePermissions } from '../types/role.types'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import RolePermissionsEditor from '../components/RolePermissionsEditor'

export default function RoleEditPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user: authUser } = useAuth()

  const [role, setRole] = useState<RoleResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Form state
  const [displayName, setDisplayName] = useState('')
  const [description, setDescription] = useState('')
  const [isActive, setIsActive] = useState(true)
  const [permissions, setPermissions] = useState<RolePermissions>({})
  const [catalog, setCatalog] = useState<PermissionCatalogItem[]>([])

  const isSuperAdmin = authUser?.role === 'SUPER_ADMIN'


  const loadRole = async () => {
    if (!id) return

    try {
      setIsLoading(true)
      const data = await rolesService.getById(id)

      if (!isSuperAdmin) {
        toast.error('Solo SUPER_ADMIN puede modificar roles')
        navigate('/roles')
        return
      }

      setRole(data)
      setDisplayName(data.display_name)
      setDescription(data.description || '')
      setIsActive(data.is_active)

      // Los permisos reales viven en role_permissions, no en el JSONB legacy
      // `data.permissions` (bug real encontrado 2026-08-26: este formulario
      // cargaba y guardaba contra ese campo muerto -- el editor siempre
      // arrancaba vacío sin importar los permisos reales del rol, y guardar
      // acá no tenía ningún efecto).
      const permData = await permissionsAssignmentService.getForRole(id)
      setCatalog(permData.catalog)
      setPermissions(idsToPermissionsDict(permData.assigned_permission_ids, permData.catalog))
    } catch (error) {
      console.error('Error al cargar rol:', error)
      toast.error('Error al cargar el rol')
      navigate('/roles')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadRole()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!role) return

    // Validaciones
    if (!displayName.trim()) {
      toast.error('El nombre para mostrar es requerido')
      return
    }

    if (!isSuperAdmin) {
      toast.error('Solo SUPER_ADMIN puede modificar roles')
      return
    }

    try {
      setIsSubmitting(true)

      const updateData: RoleUpdate = {
        display_name: displayName,
        description: description || undefined,
        // Sin efecto real (Role.permissions es JSONB legacy) -- se manda igual
        // porque el schema lo pide. El cambio real de permisos va por el PUT
        // de abajo, contra role_permissions.
        permissions,
        is_active: isActive
      }

      await rolesService.update(role.id, updateData)
      await permissionsAssignmentService.updateForRole(role.id, permissionsDictToIds(permissions, catalog))
      toast.success('Rol actualizado correctamente')
      navigate(`/roles/${role.id}`)
    } catch (error: unknown) {
      console.error('Error al actualizar rol:', error)
      const message = error instanceof Error ? error.message : 'Error al actualizar rol'
      toast.error(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600"></div>
          <p className="mt-2 text-sm text-muted-foreground">Cargando rol...</p>
        </div>
      </div>
    )
  }

  if (!role) {
    return (
      <div className="p-6">
        <p className="text-muted-foreground">Rol no encontrado</p>
      </div>
    )
  }

  return (
    <div className="w-full">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className="size-4" />} onClick={() => navigate(`/roles/${role.id}`)}>
            Volver
          </Button>
          <div className="w-px h-8 bg-border" />
          <div className="w-12 h-12 bg-linear-to-br from-brand-400 to-brand-600 rounded-xl flex items-center justify-center">
            <Shield className="text-white" size={24} />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-foreground">Editar Rol</h1>
            <p className="text-muted-foreground">
              Modifica la información del rol {role.display_name}
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
                label="Nombre del rol"
                value={role.name}
                disabled
                helperText="El nombre no puede ser modificado"
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
            onClick={() => navigate(`/roles/${role.id}`)}
            disabled={isSubmitting}
          >
            Cancelar
          </Button>
          <Button type="submit" variant="primary" leftIcon={<Save size={18} />} isLoading={isSubmitting}>
            Guardar Cambios
          </Button>
        </div>
      </form>
    </div>
  )
}
