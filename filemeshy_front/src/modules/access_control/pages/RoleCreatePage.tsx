/**
 * PÁGINA: CREAR ROL
 * Formulario para crear un nuevo rol
 */

import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Save, Shield } from 'lucide-react'
import { Button } from '../../../ui/buttons/Button'
import { Input } from '../../../ui/inputs/Input'
import { Textarea } from '../../../ui/inputs/Textarea'
import { Switch } from '../../../ui/inputs/Switch'
import { toast } from 'sonner'
import { rolesService } from '../services/roles.service'
import { permissionsAssignmentService, permissionsDictToIds, type PermissionCatalogItem } from '../services/permissions-assignment.service'
import type { RoleCreate, RolePermissions } from '../types/role.types'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import { extractErrorMessage } from '@/shared/utils/errors'
import RolePermissionsEditor from '../components/RolePermissionsEditor'

const MAX_ERROR_LENGTH = 200

/** Mensaje útil para el alta: usa el `detail` del backend (409 nombre duplicado, 422 ids inválidos) truncado. */
function buildCreateErrorMessage(error: unknown): string {
  const status = (error as { response?: { status?: number } } | null)?.response?.status
  const fallback = status === 409 ? 'Ya existe un rol con ese nombre' : 'Error al crear rol'
  const message = extractErrorMessage(error, fallback)
  // extractErrorMessage devuelve el mensaje genérico de axios si no hay detail: mejor el fallback
  const isGeneric = /^Request failed with status code/.test(message)
  const text = isGeneric ? fallback : message
  return text.length > MAX_ERROR_LENGTH ? `${text.slice(0, MAX_ERROR_LENGTH)}…` : text
}

/**
 * Catálogo de permisos con sus ids reales. Solo se expone vía
 * GET /roles/{id}/permissions, y es global (no depende del rol), así que se
 * consulta a través de cualquier rol existente.
 */
async function loadPermissionCatalog(): Promise<PermissionCatalogItem[]> {
  const list = await rolesService.list({ limit: 1 })
  const anyRole = list.items[0]
  if (!anyRole) throw new Error('No se pudo obtener el catálogo de permisos')
  return (await permissionsAssignmentService.getForRole(anyRole.id)).catalog
}

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

  const isSuperAdmin = authUser?.role === 'SUPER_ADMIN'

  // Validación del nombre derivada (sin estado ni efecto)
  const nameError = useMemo(() => {
    if (!name) return ''
    const validation = rolesService.validateRoleName(name)
    return validation.valid ? '' : validation.error || ''
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

      // Resolver los permission_id reales ANTES de crear: el rol y sus permisos se
      // persisten en un solo POST (atómico en el backend). Si algún código elegido
      // no existe en el catálogo, no se descarta en silencio: se avisa y no se crea.
      let permissionIds: string[] = []
      if (Object.values(permissions).some((actions) => (actions || []).length > 0)) {
        const catalog = await loadPermissionCatalog()
        const known = new Set(catalog.map((p) => p.permission_code))
        const missing = Object.entries(permissions).flatMap(([resource, actions]) =>
          (actions || []).map((action) => `${resource}.${action}`).filter((code) => !known.has(code))
        )
        if (missing.length > 0) {
          toast.error(`Hay permisos que ya no existen en el catálogo: ${missing.join(', ')}. Recarga la página e inténtalo de nuevo.`)
          return
        }
        permissionIds = permissionsDictToIds(permissions, catalog)
      }

      const createData: RoleCreate = {
        name: name.toUpperCase(),
        display_name: displayName,
        description: description || undefined,
        // Role.permissions (JSONB) no tiene ningún lector real en el backend --
        // se manda igual porque el schema lo pide; el efecto real viene de
        // permission_ids (tabla role_permissions, misma transacción del alta).
        permissions,
        permission_ids: permissionIds.length > 0 ? permissionIds : undefined,
        is_active: isActive
      }

      const newRole = await rolesService.create(createData)

      toast.success('Rol creado correctamente')
      navigate(`/roles/${newRole.id}`)
    } catch (error: unknown) {
      console.error('Error al crear rol:', error)
      toast.error(buildCreateErrorMessage(error))
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
                rows={4}
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
