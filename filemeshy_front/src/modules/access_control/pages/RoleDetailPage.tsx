/**
 * PÁGINA: DETALLE DE ROL
 * Vista de solo lectura de un rol
 */

import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Shield,
  ShieldCheck,
  Users,
  Edit,
  Trash2,
  Lock,
  Unlock,
  InfinityIcon
} from 'lucide-react'
import { Button } from '../../../ui/buttons/Button'
import { Badge } from '../../../ui/badges/Badge'
import { toast } from 'sonner'
import { rolesService } from '../services/roles.service'
import { permissionsAssignmentService, type PermissionCatalogItem } from '../services/permissions-assignment.service'
import type { RoleResponse } from '../types/role.types'
import { RESOURCE_LABELS } from '../types/role.types'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import DeleteConfirmDialog from '../../../ui/dialogs/DeleteConfirmDialog'
import { formatDateTime } from '../../../shared/utils/dates'

export default function RoleDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user: authUser } = useAuth()

  const [role, setRole] = useState<RoleResponse | null>(null)
  const [assignedPermissions, setAssignedPermissions] = useState<PermissionCatalogItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [deletingRole, setDeletingRole] = useState(false)

  const isSuperAdmin = authUser?.role === 'SUPER_ADMIN'
  // El rol SUPER_ADMIN (no el usuario logueado -- ver isSuperAdmin arriba) es el
  // caso especial de todo esto: role_permissions NUNCA fue su fuente real de
  // acceso (bypass explícito en has_permission()), así que la lista puntual que
  // sí tiene (residual de un par de migraciones, ver PENDIENTES.md) confunde más
  // de lo que aclara. Se muestra "Acceso total" en vez de esa lista parcial.
  const isSuperAdminRole = role?.name === 'SUPER_ADMIN'

  useEffect(() => {
    loadRole()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const loadRole = async () => {
    if (!id) return

    try {
      setIsLoading(true)
      // El rol trae display_name/is_active/users_count/etc, pero sus permisos
      // reales viven en la tabla role_permissions (role.permissions es el JSONB
      // legacy, siempre vacío) -- se cargan aparte con el mismo endpoint que usa
      // el editor de permisos (GET /roles/{id}/permissions).
      const [roleData, permData] = await Promise.all([
        rolesService.getById(id),
        permissionsAssignmentService.getForRole(id),
      ])
      setRole(roleData)
      const assignedIds = new Set(permData.assigned_permission_ids)
      setAssignedPermissions(permData.catalog.filter((p) => assignedIds.has(p.id)))
    } catch (error) {
      console.error('Error al cargar rol:', error)
      toast.error('Error al cargar el rol')
      navigate('/roles')
    } finally {
      setIsLoading(false)
    }
  }

  const handleEdit = () => {
    if (!role) return
    navigate(`/roles/${role.id}/editar`)
  }

  const handleDelete = () => {
    if (!role) return

    if (!rolesService.canDeleteRole(role)) {
      if (role.is_system) {
        toast.error('Los roles del sistema no pueden ser eliminados')
      } else if (role.users_count && role.users_count > 0) {
        toast.error(`No se puede eliminar: ${role.users_count} usuario(s) asignado(s)`)
      } else {
        toast.error('Este rol no puede ser eliminado')
      }
      return
    }

    setDeletingRole(true)
  }

  const confirmDelete = async () => {
    if (!role) return

    try {
      await rolesService.delete(role.id)
      toast.success('Rol eliminado correctamente')
      navigate('/roles')
    } catch (error) {
      console.error('Error al eliminar rol:', error)
      toast.error(error instanceof Error ? error.message : 'Error al eliminar rol')
    } finally {
      setDeletingRole(false)
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

  const permissionsByCategory = assignedPermissions.reduce((acc, perm) => {
    const category = perm.resource || perm.permission_category || 'general'
    if (!acc[category]) acc[category] = []
    acc[category].push(perm)
    return acc
  }, {} as Record<string, PermissionCatalogItem[]>)

  return (
    <div className="w-full">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className="size-4" />} onClick={() => navigate('/roles')}>
              Volver
            </Button>
            <div className="w-px h-8 bg-border" />
            <div className="w-16 h-16 bg-linear-to-br from-brand-400 to-brand-600 rounded-xl flex items-center justify-center">
              {role.is_system ? (
                <ShieldCheck className="text-white" size={32} />
              ) : (
                <Shield className="text-white" size={32} />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h1 className="text-3xl font-bold text-foreground">
                  {role.display_name}
                </h1>
                {role.is_system && (
                  <Badge variant="info" size="sm">
                    Sistema
                  </Badge>
                )}
                <Badge variant={role.is_active ? 'success' : 'gray'} size="sm">
                  {role.is_active ? 'Activo' : 'Inactivo'}
                </Badge>
              </div>
              <p className="text-muted-foreground">
                {role.description || 'Sin descripción'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {isSuperAdmin && rolesService.canModifyRole(role) && (
              <Button variant="primary" onClick={handleEdit} leftIcon={<Edit size={18} />}>
                Editar
              </Button>
            )}
            {isSuperAdmin && rolesService.canDeleteRole(role) && (
              <Button variant="danger" onClick={handleDelete} leftIcon={<Trash2 size={18} />}>
                Eliminar
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Información General */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-muted rounded-xl shadow-xs border border-border p-6">
          <div className="flex items-center gap-3 mb-2">
            <Users className="text-brand-600" size={24} />
            <span className="text-sm text-muted-foreground">Usuarios Asignados</span>
          </div>
          <p className="text-3xl font-bold text-foreground">
            {role.users_count || 0}
          </p>
        </div>

        <div className="bg-muted rounded-xl shadow-xs border border-border p-6">
          <div className="flex items-center gap-3 mb-2">
            {isSuperAdminRole ? (
              <InfinityIcon className="text-blue-600" size={24} />
            ) : (
              <Shield className="text-blue-600" size={24} />
            )}
            <span className="text-sm text-muted-foreground">Permisos</span>
          </div>
          {isSuperAdminRole ? (
            <p className="text-lg font-semibold text-foreground">Acceso total</p>
          ) : (
            <p className="text-3xl font-bold text-foreground">
              {assignedPermissions.length}
            </p>
          )}
        </div>

        <div className="bg-muted rounded-xl shadow-xs border border-border p-6">
          <div className="flex items-center gap-3 mb-2">
            {role.can_be_modified ? (
              <Unlock className="text-green-600" size={24} />
            ) : (
              <Lock className="text-red-600" size={24} />
            )}
            <span className="text-sm text-muted-foreground">Estado</span>
          </div>
          <p className="text-lg font-semibold text-foreground">
            {role.can_be_modified ? 'Modificable' : 'Bloqueado'}
          </p>
        </div>
      </div>

      {/* Detalles */}
      <div className="bg-muted rounded-xl shadow-xs border border-border p-6 mb-6">
        <h2 className="text-lg font-semibold text-foreground mb-4">
          Información del Rol
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-muted-foreground">
              Nombre Interno
            </label>
            <p className="text-foreground font-mono">{role.name}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-muted-foreground">
              Nombre para Mostrar
            </label>
            <p className="text-foreground">{role.display_name}</p>
          </div>
          <div className="md:col-span-2">
            <label className="text-sm font-medium text-muted-foreground">
              Descripción
            </label>
            <p className="text-foreground">
              {role.description || 'Sin descripción'}
            </p>
          </div>
          <div>
            <label className="text-sm font-medium text-muted-foreground">
              Creado
            </label>
            <p className="text-foreground">
              {formatDateTime(role.created_at) ?? ''}
            </p>
          </div>
          <div>
            <label className="text-sm font-medium text-muted-foreground">
              Última Actualización
            </label>
            <p className="text-foreground">
              {formatDateTime(role.updated_at) ?? ''}
            </p>
          </div>
        </div>
      </div>

      {/* Permisos */}
      <div className="bg-muted rounded-xl shadow-xs border border-border p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4">
          Permisos del Rol
        </h2>
        {isSuperAdminRole ? (
          <div className="flex items-start gap-3 rounded-lg bg-card px-4 py-3">
            <InfinityIcon className="text-blue-600 shrink-0 mt-0.5" size={20} />
            <p className="text-sm text-foreground/80">
              <strong>SUPER_ADMIN tiene acceso total al sistema por diseño</strong> — no
              depende de una lista de permisos asignados, un chequeo explícito en el
              backend le da acceso a todo sin excepción. La tabla de asignaciones
              (`role_permissions`) puede tener algunas filas puntuales para este rol
              (residuo de migraciones anteriores), pero no reflejan ni limitan su
              acceso real.
            </p>
          </div>
        ) : Object.keys(permissionsByCategory).length === 0 ? (
          <p className="text-muted-foreground text-center py-8">
            No hay permisos configurados
          </p>
        ) : (
          <div className="space-y-6">
            {Object.entries(permissionsByCategory).map(([category, perms]) => (
              <div key={category}>
                <h3 className="text-sm font-semibold text-foreground/80 mb-3 uppercase">
                  {RESOURCE_LABELS[category] || category}
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                  {perms.map((perm) => (
                    <div
                      key={perm.id}
                      className="flex flex-col gap-1 px-3 py-2 rounded-lg bg-card"
                    >
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-green-500" />
                        <span className="text-sm font-medium text-foreground/80">
                          {perm.permission_name}
                        </span>
                      </div>
                      <div className="ml-4 text-xs text-muted-foreground font-mono">
                        {perm.permission_code}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmDialog
        isOpen={deletingRole}
        onClose={() => setDeletingRole(false)}
        onConfirm={confirmDelete}
        title="Eliminar Rol"
        description={`¿Estás seguro de que deseas eliminar el rol "${role.display_name}"? Esta acción no se puede deshacer.`}
      />
    </div>
  )
}
