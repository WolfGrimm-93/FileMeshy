/**
 * PÁGINA: GESTIÓN DE ROLES
 * Gestión de roles dinámicos del sistema
 */

import { parseDate } from '@/shared/utils/dates'
import { useMemo, useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Plus,
  Shield,
  ShieldCheck,
  RefreshCw,
  Users,
  Lock,
  Trash2,
  ShieldAlert
} from 'lucide-react'
import { DataTable } from '@/ui/tables/DataTable'
import { TableFilters } from '@/ui/tables/TableFilters'
import { Button } from '@/ui/buttons/Button'
import { Badge } from '@/ui/badges/Badge'
import { EmptyState } from '@/ui/empty-states/EmptyState'
import { toast } from 'sonner'
import { rolesService } from '../services/roles.service'
import type { RoleResponse } from '../types/role.types'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import DeleteConfirmDialog from '@/ui/dialogs/DeleteConfirmDialog'

export default function RolesManagementPage() {
  const navigate = useNavigate()
  const { user: authUser } = useAuth()

  // Estados
  const [roles, setRoles] = useState<RoleResponse[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isFirstLoad, setIsFirstLoad] = useState(true)
  const [permissionError, setPermissionError] = useState(false)
  const [selectedRoles, setSelectedRoles] = useState<string[]>([])

  // Filtros -- mismo patrón que UsuariosPage: búsqueda + Estado (Activos por
  // defecto), sin filtro de tipo (Sistema/Personalizado no aporta acá, todos los
  // roles reales del sistema son "Sistema").
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('activo')

  // Modal
  const [deletingRole, setDeletingRole] = useState<RoleResponse | null>(null)

  // Verificar si es SUPER_ADMIN
  const isSuperAdmin = authUser?.role === 'SUPER_ADMIN'

  // Núcleo del fetch: sin setState síncrono (isLoading arranca en true y
  // permissionError en false), así lo puede usar el efecto de montaje
  const fetchRoles = useCallback(
    () =>
      rolesService
        .list({
          skip: 0,
          limit: 100,
          include_system: true
        })
        .then((response) => {
          setRoles(response.items)
        })
        .catch((error: unknown) => {
          console.error('Error al cargar roles:', error)
          const err = error as { status?: number; response?: { status?: number }; message?: string }
          if (err?.status === 403 || err?.response?.status === 403) {
            setPermissionError(true)
          }
        })
        .finally(() => {
          setIsLoading(false)
          setIsFirstLoad(false)
        }),
    []
  )

  // Recarga (handlers, intervalo): marca loading y limpia el error antes del fetch
  const loadRoles = useCallback(async () => {
    setIsLoading(true)
    setPermissionError(false)
    await fetchRoles()
  }, [fetchRoles])

  // Cargar al montar
  useEffect(() => {
    fetchRoles()
  }, [fetchRoles])

  // Auto-refresh cada 30s
  useEffect(() => {
    if (permissionError) return

    const interval = setInterval(() => {
      loadRoles().catch(() => {
        // Error ya manejado en loadRoles
      })
    }, 30000)
    return () => clearInterval(interval)
  }, [permissionError, loadRoles])

  // Filtrar roles
  const filteredRoles = useMemo(() => {
    let filtered = roles

    // Filtro de búsqueda
    if (searchTerm) {
      const search = searchTerm.toLowerCase()
      filtered = filtered.filter(
        (role) =>
          role.name.toLowerCase().includes(search) ||
          role.display_name.toLowerCase().includes(search) ||
          (role.description && role.description.toLowerCase().includes(search))
      )
    }

    // Filtro de estado
    if (statusFilter === 'activo') {
      filtered = filtered.filter((role) => role.is_active)
    } else if (statusFilter === 'inactivo') {
      filtered = filtered.filter((role) => !role.is_active)
    }

    return filtered
  }, [roles, searchTerm, statusFilter])

  // Calcular estadísticas
  const estadisticas = useMemo(() => {
    return {
      total: roles.length,
      activos: roles.filter((r) => r.is_active).length,
      inactivos: roles.filter((r) => !r.is_active).length,
      sistema: roles.filter((r) => r.is_system).length,
      personalizados: roles.filter((r) => !r.is_system).length,
      totalUsuarios: roles.reduce((acc, r) => acc + (r.users_count || 0), 0)
    }
  }, [roles])

  // Mapear roles para la tabla
  const mappedRoles = useMemo(() => {
    return filteredRoles.map((role) => ({
      id: role.id.toString(),
      nombre: role.name,
      nombreMostrar: role.display_name,
      descripcion: role.description || '-',
      tipo: role.is_system ? 'Sistema' : 'Personalizado',
      estado: role.is_active ? 'activo' : 'inactivo',
      usuarios: role.users_count || 0,
      permisos: role.permissions_count ?? 0,
      esModificable: role.can_be_modified ?? !role.is_system,
      esEliminable: role.can_be_deleted ?? !role.is_system,
      fechaCreacion: parseDate(role.created_at),
      rawRole: role
    }))
  }, [filteredRoles])

  type MappedRole = typeof mappedRoles[number]

  // Handlers
  const handleCreate = () => {
    navigate('/roles/nuevo')
  }

  const handleEdit = (roleId: string) => {
    const role = roles.find((r) => r.id.toString() === roleId)
    if (!role) return

    if (!rolesService.canModifyRole(role)) {
      toast.error('Este rol no puede ser modificado')
      return
    }

    navigate(`/roles/${roleId}/editar`)
  }

  const handleViewPermissions = (roleId: string) => {
    navigate(`/roles/${roleId}`)
  }

  const handleDelete = (roleId: string) => {
    const role = roles.find((r) => r.id.toString() === roleId)
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

    if (!isSuperAdmin) {
      toast.error('Solo SUPER_ADMIN puede eliminar roles')
      return
    }

    setDeletingRole(role)
  }

  const confirmDelete = async () => {
    if (!deletingRole) return

    try {
      await rolesService.delete(deletingRole.id)
      toast.success('Rol eliminado correctamente')
      await loadRoles()
    } catch (error: unknown) {
      console.error('Error al eliminar rol:', error)
      toast.error(error instanceof Error ? error.message : 'Error al eliminar rol')
    } finally {
      setDeletingRole(null)
    }
  }

  // Handler para eliminar roles seleccionados
  const handleBulkDelete = async () => {
    if (selectedRoles.length === 0) return

    // Verificar que todos los roles seleccionados se puedan eliminar
    const rolesToDelete = selectedRoles
      .map((id) => roles.find((r) => r.id.toString() === id))
      .filter((r): r is RoleResponse => r !== undefined)

    const cannotDelete = rolesToDelete.filter((r) => !rolesService.canDeleteRole(r))

    if (cannotDelete.length > 0) {
      toast.error(
        `No se pueden eliminar ${cannotDelete.length} rol(es): roles del sistema o con usuarios asignados`
      )
      return
    }

    const confirmMessage =
      selectedRoles.length === 1
        ? '¿Estás seguro de eliminar este rol?'
        : `¿Estás seguro de eliminar ${selectedRoles.length} roles seleccionados?`

    if (!confirm(confirmMessage)) return

    try {
      await Promise.all(selectedRoles.map((id) => rolesService.delete(id)))
      toast.success(
        selectedRoles.length === 1
          ? 'Rol eliminado correctamente'
          : `${selectedRoles.length} roles eliminados correctamente`
      )
      setSelectedRoles([])
      await loadRoles()
    } catch (error: unknown) {
      console.error('Error al eliminar roles:', error)
      toast.error('Error al eliminar roles')
    }
  }

  // Handler para reintentar carga
  const handleRetry = () => {
    setPermissionError(false)
    setIsFirstLoad(true)
    loadRoles()
  }

  // Columnas de la tabla
  const columns: Array<{
    key: keyof MappedRole;
    label: string;
    sortable?: boolean;
    render?: (value: unknown, row: MappedRole) => React.ReactNode;
  }> = [
    {
      key: 'nombre',
      label: 'Nombre',
      sortable: true,
      render: (value: unknown, row: MappedRole) => {
        const nombre = value as string
        return (
          <div className="flex items-center gap-2">
            {row.rawRole.is_system ? (
              <ShieldCheck className="w-4 h-4 text-blue-500" />
            ) : (
              <Shield className="w-4 h-4 text-gray-400" />
            )}
            <span className="font-mono font-medium">{nombre}</span>
          </div>
        )
      }
    },
    {
      key: 'nombreMostrar',
      label: 'Nombre para mostrar',
      sortable: true
    },
    {
      key: 'tipo',
      label: 'Tipo',
      sortable: true,
      render: (value: unknown) => {
        const tipo = value as string
        return (
          <Badge variant={tipo === 'Sistema' ? 'primary' : 'gray'}>
            {tipo}
          </Badge>
        )
      }
    },
    {
      key: 'usuarios',
      label: 'Usuarios',
      sortable: true,
      render: (value: unknown) => {
        const usuarios = value as number
        return (
          <div className="flex items-center justify-center gap-1">
            <Users className="w-4 h-4 text-gray-400" />
            <span>{usuarios}</span>
          </div>
        )
      }
    },
    {
      key: 'permisos',
      label: 'Permisos',
      sortable: true,
      render: (value: unknown, row: MappedRole) => {
        const permisos = value as number
        // SUPER_ADMIN no depende de role_permissions para su acceso (bypass
        // explícito en el backend) -- mostrar el conteo puntual ahí confunde,
        // mismo criterio ya aplicado en RoleDetailPage.tsx.
        if (row.rawRole.name === 'SUPER_ADMIN') {
          return (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleViewPermissions(row.id)}
              className="text-primary hover:text-primary-dark"
            >
              <Lock className="w-4 h-4 mr-1" />
              Acceso total
            </Button>
          )
        }
        return (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => handleViewPermissions(row.id)}
            className="text-primary hover:text-primary-dark"
          >
            <Lock className="w-4 h-4 mr-1" />
            {permisos} recursos
          </Button>
        )
      }
    },
    {
      key: 'estado',
      label: 'Estado',
      sortable: true,
      render: (value: unknown) => {
        const estado = value as string
        return (
          <Badge variant={estado === 'activo' ? 'success' : 'gray'}>
            {estado === 'activo' ? 'Activo' : 'Inactivo'}
          </Badge>
        )
      }
    }
  ]

  // Acciones de la tabla
  const actions = [
    {
      icon: 'view' as const,
      label: 'Ver detalles',
      onClick: (row: MappedRole) => handleViewPermissions(row.id)
    },
    {
      icon: 'edit' as const,
      label: 'Editar',
      onClick: (row: MappedRole) => {
        if (!row.esModificable) {
          toast.error('Este rol no puede ser modificado')
          return
        }
        handleEdit(row.id)
      }
    },
    {
      icon: 'delete' as const,
      label: 'Eliminar',
      onClick: (row: MappedRole) => {
        if (!row.esEliminable) {
          toast.error('Este rol no puede ser eliminado')
          return
        }
        handleDelete(row.id)
      },
      color: 'text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300'
    }
  ]

  // UI de error de permisos
  if (permissionError && !isFirstLoad) {
    return (
      <div className="space-y-6">
        {/* Header */}
        <div className="bg-card rounded-lg border border-border p-6">
          <div className="flex items-start gap-3">
            <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className="size-4" />} onClick={() => navigate('/usuarios')}>
              Volver
            </Button>
            <div className="w-px h-8 bg-border" />
            <div>
              <h1 className="text-3xl font-bold text-foreground">
                Gestión de Roles
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Administra los roles y permisos del sistema
              </p>
            </div>
          </div>
        </div>

        {/* Error de Permisos */}
        <div className="bg-card rounded-lg border border-border p-12">
          <div className="flex flex-col items-center justify-center text-center max-w-md mx-auto">
            <div className="w-16 h-16 bg-red-100 dark:bg-red-900/20 rounded-full flex items-center justify-center mb-4">
              <Lock className="w-8 h-8 text-red-600 dark:text-red-400" />
            </div>

            <h2 className="text-2xl font-bold text-foreground mb-2">
              Acceso Denegado
            </h2>
            <p className="text-muted-foreground mb-6">
              No tienes permisos para ver la gestión de roles. Este módulo requiere permisos de
              administrador.
            </p>

            {/* Información adicional */}
            <div className="bg-brand-50 dark:bg-brand-900/20 border border-brand-200 dark:border-brand-800 rounded-lg p-4 mb-6 w-full">
              <div className="flex items-start gap-3">
                <ShieldAlert className="w-5 h-5 text-primary shrink-0 mt-0.5" />
                <div className="text-left">
                  <h3 className="text-sm font-semibold text-brand-900 dark:text-brand-100 mb-1">
                    ¿Por qué veo este mensaje?
                  </h3>
                  <ul className="text-sm text-brand-800 dark:text-brand-200 space-y-1">
                    <li>• Tu cuenta no tiene el rol de Administrador o Super Admin</li>
                    <li>• Solo usuarios con permisos especiales pueden gestionar roles</li>
                    <li>• Contacta a tu administrador si necesitas acceso</li>
                  </ul>
                </div>
              </div>
            </div>

            {/* Botones */}
            <div className="flex gap-3">
              <Button variant="secondary" leftIcon={<RefreshCw className="w-4 h-4" />} onClick={handleRetry}>
                Reintentar
              </Button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header con Estadísticas y Acciones */}
      <div className="mb-6">
        {/* Fila superior: Título y Botones */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-start gap-3">
            <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className="size-4" />} onClick={() => navigate('/usuarios')}>
              Volver
            </Button>
            <div className="w-px h-8 bg-border" />
            <div>
              <h1 className="text-3xl font-bold text-foreground">Gestión de Roles</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Administra los roles y permisos del sistema
              </p>
            </div>
          </div>

          <div className="flex gap-2">
            {/* Botón de eliminar seleccionados (solo para superadmin) */}
            {isSuperAdmin && selectedRoles.length > 0 && (
              <Button
                variant="danger"
                leftIcon={<Trash2 className="w-4 h-4" />}
                onClick={handleBulkDelete}
              >
                Eliminar ({selectedRoles.length})
              </Button>
            )}

            {isSuperAdmin && (
              <Button variant="primary" leftIcon={<Plus className="w-4 h-4" />} onClick={handleCreate}>
                Nuevo Rol
              </Button>
            )}
          </div>
        </div>

        {/* Stats Grid con separadores verticales */}
        <div className="flex items-center gap-6 divide-x divide-border">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-muted rounded-lg">
              <Shield className="w-5 h-5 text-muted-foreground" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Total</p>
              <p className="text-lg font-semibold text-foreground">
                {estadisticas.total}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 pl-6">
            <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
              <ShieldCheck className="w-5 h-5 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <p className="text-xs text-green-600 dark:text-green-500">Activos</p>
              <p className="text-lg font-semibold text-green-700 dark:text-green-400">
                {estadisticas.activos}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 pl-6">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <ShieldAlert className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-xs text-blue-600 dark:text-blue-500">Sistema</p>
              <p className="text-lg font-semibold text-blue-700 dark:text-blue-400">
                {estadisticas.sistema}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 pl-6">
            <div className="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-lg">
              <Shield className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <p className="text-xs text-purple-600 dark:text-purple-500">Personalizados</p>
              <p className="text-lg font-semibold text-purple-700 dark:text-purple-400">
                {estadisticas.personalizados}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 pl-6">
            <div className="p-2 bg-brand-100 dark:bg-brand-900/30 rounded-lg">
              <Users className="w-5 h-5 text-primary" />
            </div>
            <div>
              <p className="text-xs text-primary">Usuarios Asignados</p>
              <p className="text-lg font-semibold text-primary">
                {estadisticas.totalUsuarios}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Filtros -- mismo patrón que UsuariosPage: búsqueda + Estado en botones */}
      <TableFilters
        enableSearch
        searchValue={searchTerm}
        onSearchChange={setSearchTerm}
        searchPlaceholder="Buscar por nombre o descripción..."
        enableFilters
        statusFilters={[
          { key: 'activo', label: 'Activos', value: 'activo', count: estadisticas.activos },
          { key: 'inactivo', label: 'Inactivos', value: 'inactivo', count: estadisticas.inactivos },
          { key: 'all', label: 'Todos', value: 'all', count: estadisticas.total },
        ]}
        activeFilter={statusFilter}
        onFilterChange={(value) => setStatusFilter(value as string)}
      />

      {/* Table */}
      {isFirstLoad ? (
        <div className="bg-card rounded-lg border border-border p-12">
          <div className="flex flex-col items-center justify-center">
            <div className="w-12 h-12 border-4 border-brand-500 border-t-transparent rounded-full animate-spin mb-4"></div>
            <p className="text-muted-foreground">Cargando roles...</p>
          </div>
        </div>
      ) : mappedRoles.length === 0 && !isLoading ? (
        <div
          className="flex items-center justify-center bg-linear-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800 border border-border rounded-xl shadow-xs"
          style={{ minHeight: '550px' }}
        >
          <EmptyState
            icon={
              <Shield className="size-20 text-muted-foreground" strokeWidth={1.5} />
            }
            title={searchTerm || statusFilter !== 'all' ? 'No se encontraron roles' : 'No hay roles registrados'}
            description={
              searchTerm || statusFilter !== 'all'
                ? 'Intenta cambiar los filtros de búsqueda.'
                : 'Comienza a gestionar permisos agregando el primer rol personalizado. Podrás asignar permisos específicos y administrar el acceso al sistema.'
            }
          />
        </div>
      ) : (
        <div className={isLoading ? 'opacity-70 transition-opacity' : ''}>
          <DataTable
            headers={columns}
            data={mappedRoles}
            actions={actions}
            enableSelection={isSuperAdmin}
            selectedRows={selectedRoles}
            onSelectionChange={(ids) => setSelectedRoles([...ids].map(String))}
            enableSort
            enableActions
          />
        </div>
      )}

      {/* Modales */}
      {deletingRole && (
        <DeleteConfirmDialog
          isOpen={true}
          onClose={() => setDeletingRole(null)}
          onConfirm={confirmDelete}
          title="Eliminar rol"
          description={`¿Estás seguro de eliminar el rol "${deletingRole.display_name}"? Esta acción no se puede deshacer.`}
        />
      )}
    </div>
  )
}
