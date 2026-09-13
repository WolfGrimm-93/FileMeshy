/**
 * PÁGINA: USUARIOS
 * Gestión de usuarios del sistema
 */

import { useEffect, useState, useRef, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Lock, ShieldAlert, RefreshCw, Users, UserCheck, UserX, ShieldCheck, KeyRound } from 'lucide-react'
import { useUserStore } from '@/modules/users/store/userStore'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import { Button } from '@/ui/buttons/Button'
import { Badge } from '@/ui/badges/Badge'
import { DataTable, type Column, type TableAction } from '@/ui/tables/DataTable'
import { TableFilters } from '@/ui/tables/TableFilters'
import { TablePagination } from '@/ui/tables/TablePagination'
import { FilterButton, FilterModal, FilterChips, countActiveFilters, type FilterGroup, type FilterValues } from '@/ui/filters'
import { StatsGrid } from '@/ui/stats/StatsGrid'
import { ConfirmDialog } from '@/ui/modals/ConfirmDialog'
import { EmptyState } from '@/ui/empty-states/EmptyState'
import { toast } from '@/ui/toast/CustomToast'
import type { User } from '@/modules/users/services/user.service'

// =============================================
// Columnas definidas fuera del componente (estables)
// =============================================

const roleVariants: Record<string, 'primary' | 'success' | 'info' | 'warning' | 'gray'> = {
  SUPER_ADMIN: 'primary',
  ADMIN: 'success',
  USER: 'warning',
}

const roleLabels: Record<string, string> = {
  SUPER_ADMIN: 'Super Admin',
  ADMIN: 'Administrador',
  USER: 'Usuario',
}

const columns: Column<User>[] = [
  {
    key: 'first_name',
    label: 'Nombre',
    render: (_value, row) => (
      <span className="text-sm font-medium">{row.first_name} {row.last_name}</span>
    ),
  },
  {
    key: 'email',
    label: 'Email',
    render: (value) => <span className="text-sm">{value as string}</span>,
  },
  {
    key: 'phone',
    label: 'Teléfono',
    width: '120px',
    render: (value) => (
      <span className="text-sm text-muted-foreground">{(value as string) || '-'}</span>
    ),
  },
  {
    key: 'role',
    label: 'Rol',
    width: '130px',
    render: (value) => {
      const role = value as string
      const variant = roleVariants[role] || 'gray'
      const label = roleLabels[role] || role
      return <Badge variant={variant} size="sm">{label}</Badge>
    },
  },
  {
    key: 'last_login',
    label: 'Último Acceso',
    width: '140px',
    render: (value) => {
      if (!value) {
        return <span className="text-sm text-muted-foreground italic">Nunca</span>
      }
      try {
        const date = new Date(value as string)
        if (isNaN(date.getTime())) return <span className="text-sm text-muted-foreground">-</span>
        const diffMinutes = (Date.now() - date.getTime()) / (1000 * 60)

        if (diffMinutes < 5) {
          return <span className="text-sm text-green-600 dark:text-green-400 font-semibold">Ahora</span>
        } else if (diffMinutes < 60) {
          return <span className="text-sm text-green-600 dark:text-green-400">Hace {Math.floor(diffMinutes)} min</span>
        } else if (diffMinutes < 1440) {
          return <span className="text-sm text-blue-600 dark:text-blue-400">Hace {Math.floor(diffMinutes / 60)} hrs</span>
        } else {
          const days = Math.floor(diffMinutes / 1440)
          return <span className="text-sm text-muted-foreground">Hace {days} día{days > 1 ? 's' : ''}</span>
        }
      } catch {
        return <span className="text-sm text-muted-foreground">-</span>
      }
    },
  },
  {
    key: 'is_active',
    label: 'Estado',
    width: '100px',
    align: 'center',
    render: (value) => {
      const active = value as boolean
      return (
        <Badge variant={active ? 'success' : 'gray'} size="sm">
          {active ? 'Activo' : 'Inactivo'}
        </Badge>
      )
    },
  },
]

// =============================================
// COMPONENTE
// =============================================

export default function UsersListPage() {
  const navigate = useNavigate()

  const {
    users,
    total: totalItems,
    page: currentPage,
    pageSize,
    totalPages,
    filters,
    isLoading,
    globalStats = {
      total: 0,
      total_active: 0,
      total_inactive: 0,
      roles: {},
    },
    fetchUsers,
    fetchStats,
    deleteUser,
    setPage,
    setPageSize,
    setFilters,
  } = useUserStore()

  const { user: authUser } = useAuth()

  // Estado local para UI
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [userToDelete, setUserToDelete] = useState<{ id: string; name: string } | null>(null)
  const [isFirstLoad, setIsFirstLoad] = useState(true)
  const [permissionError, setPermissionError] = useState(false)
  const [isFilterModalOpen, setIsFilterModalOpen] = useState(false)

  // Derivar estado local desde el store
  const [searchTerm, setSearchTerm] = useState(() => filters.search || '')
  // Por defecto se ven solo los activos -- filters.is_active queda "undefined" tanto
  // si nunca se eligio nada como si se eligio "Todos" a proposito; el efecto de abajo
  // fuerza el default real la primera vez que se entra sin eleccion previa.
  const [estadoFilter, setEstadoFilter] = useState<string>(() =>
    filters.is_active === undefined ? 'active' : filters.is_active ? 'active' : 'inactive'
  )

  // Verificar permisos del usuario actual
  const isAdminOrHigher = authUser?.role === 'ADMIN' || authUser?.role === 'SUPER_ADMIN'

  // Helper: construir filtros desde search + estado
  const buildFilters = useCallback((search: string, estado: string) => {
    const f: { search?: string; is_active?: boolean } = {
      search: search || undefined,
    }
    if (estado === 'active') f.is_active = true
    else if (estado === 'inactive') f.is_active = false
    return f
  }, [])

  // Debounce SOLO para búsqueda por teclado (300ms)
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const handleSearchChange = useCallback((value: string) => {
    setSearchTerm(value)
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => {
      setFilters(buildFilters(value, estadoFilter))
    }, 300)
  }, [estadoFilter, setFilters, buildFilters])

  // ---- Filtro "Estado" vía el modal reutilizable (filemeshy_front/src/ui/filters) ----
  // El componente es ciego a stores: solo declara los campos (`filterGroups`) y recibe/entrega
  // un objeto plano (`FilterValues`) que acá se traduce al `buildFilters` ya existente.
  // Estado ya no vive como tabs sueltos en la tabla -- se movió adentro del modal.
  // "active" es el default (equivalente a "sin filtro explícito").

  const estadoFiltersData = useMemo(() => [
    { key: 'active', label: 'Activos', value: 'active', count: globalStats.total_active },
    { key: 'inactive', label: 'Inactivos', value: 'inactive', count: globalStats.total_inactive },
    { key: 'all', label: 'Todos', value: 'all', count: globalStats.total },
  ], [globalStats])

  const filterGroups: FilterGroup[] = useMemo(() => [
    {
      title: 'Estado',
      fields: [
        {
          key: 'estado',
          label: 'Estado del usuario',
          shortLabel: 'Estado',
          type: 'select',
          placeholder: 'Activos',
          options: estadoFiltersData
            .filter((s) => s.key !== 'active')
            .map((s) => ({ value: s.value, label: s.label, count: s.count })),
        },
      ],
    },
  ], [estadoFiltersData])

  const filterValues: FilterValues = useMemo(() => ({
    estado: estadoFilter === 'active' ? undefined : estadoFilter,
  }), [estadoFilter])

  const activeFilterCount = useMemo(
    () => countActiveFilters(filterGroups, filterValues),
    [filterGroups, filterValues]
  )

  const handleApplyModalFilters = useCallback((newValues: FilterValues) => {
    const estado = (newValues.estado as string | undefined) ?? 'active'
    setEstadoFilter(estado)
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    setFilters(buildFilters(searchTerm, estado))
  }, [searchTerm, setFilters, buildFilters])

  const handleClearModalFilters = useCallback(() => {
    handleApplyModalFilters({})
  }, [handleApplyModalFilters])

  // Quitar el chip de Estado: vuelve al default "Activos".
  const handleRemoveFilterKey = useCallback((key: string) => {
    const current: FilterValues = {
      estado: estadoFilter === 'active' ? undefined : estadoFilter,
    }
    handleApplyModalFilters({ ...current, [key]: undefined })
  }, [estadoFilter, handleApplyModalFilters])

  // Cargar stats globales una sola vez al montar
  useEffect(() => {
    fetchStats()
  }, [fetchStats])

  // Sanitizar los filtros persistidos al entrar: fuerza el default "Activos" si
  // nunca se eligio estado, y descarta un `role` que pudiera haber quedado
  // guardado en localStorage de una version anterior de esta pantalla (el filtro
  // por rol ya no existe acá).
  useEffect(() => {
    if (filters.is_active === undefined || 'role' in filters) {
      setFilters(buildFilters(filters.search || '', estadoFilter))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Fetch cuando cambian page, pageSize o filters en el store
  useEffect(() => {
    const loadData = async () => {
      try {
        await fetchUsers(true)
        setPermissionError(false)
      } catch (err: unknown) {
        const e = err as { response?: { status?: number }; status?: number }
        if (e?.response?.status === 403 || e?.status === 403) {
          setPermissionError(true)
        }
      } finally {
        setIsFirstLoad(false)
      }
    }
    loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, pageSize, filters])

  // ---- Handlers ----

  const handleDeleteConfirm = useCallback(async () => {
    if (!userToDelete) return
    try {
      await deleteUser(userToDelete.id)
      toast.success('Usuario eliminado exitosamente')
      setDeleteDialogOpen(false)
      setUserToDelete(null)
      fetchStats()
    } catch {
      toast.error('Error al eliminar usuario')
    }
  }, [userToDelete, deleteUser, fetchStats])

  // Handler para reintentar carga
  const handleRetry = useCallback(() => {
    setPermissionError(false)
    setIsFirstLoad(true)
    fetchUsers(true)
      .then(() => setPermissionError(false))
      .catch((err: unknown) => {
        const e = err as { response?: { status?: number }; status?: number }
        if (e?.response?.status === 403 || e?.status === 403) {
          setPermissionError(true)
        }
      })
      .finally(() => setIsFirstLoad(false))
  }, [fetchUsers])

  // ---- Acciones de tabla (memoizadas) ----

  const actions: TableAction<User>[] = useMemo(() => [
    {
      icon: 'view',
      label: 'Ver detalles',
      onClick: (row) => navigate(`/usuarios/${row.id}`),
    },
    {
      icon: 'edit',
      label: 'Editar',
      onClick: (row) => navigate(`/usuarios/${row.id}/editar`),
    },
    {
      icon: 'delete',
      label: 'Eliminar',
      onClick: (row) => {
        setUserToDelete({ id: row.id, name: `${row.first_name} ${row.last_name}` })
        setDeleteDialogOpen(true)
      },
    },
  ], [navigate])

  // Si hay error de permisos, mostrar UI especial
  if (permissionError) {
    return (
      <div className="space-y-6">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-foreground">Usuarios</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Gestiona los usuarios del sistema
          </p>
        </div>

        <div className="flex items-center justify-center bg-linear-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800 border border-border rounded-xl shadow-xs" style={{ minHeight: '550px' }}>
          <div className="flex flex-col items-center justify-center text-center max-w-md mx-auto">
            <div className="w-16 h-16 bg-red-100 dark:bg-red-900/20 rounded-full flex items-center justify-center mb-4">
              <Lock className="w-8 h-8 text-red-600 dark:text-red-400" />
            </div>
            <h2 className="text-2xl font-bold text-foreground mb-2">
              Acceso Denegado
            </h2>
            <p className="text-muted-foreground mb-6">
              No tienes permisos para ver la lista de usuarios. Este módulo requiere permisos de administrador.
            </p>

            <div className="bg-brand-50 dark:bg-brand-900/20 border border-brand-200 dark:border-brand-800 rounded-lg p-4 mb-6 w-full">
              <div className="flex items-start gap-3">
                <ShieldAlert className="w-5 h-5 text-primary shrink-0 mt-0.5" />
                <div className="text-left">
                  <h3 className="text-sm font-semibold text-brand-900 dark:text-brand-100 mb-1">
                    ¿Por qué veo este mensaje?
                  </h3>
                  <ul className="text-sm text-brand-800 dark:text-brand-200 space-y-1">
                    <li>Tu cuenta no tiene el rol de Administrador o Super Admin</li>
                    <li>Solo usuarios con permisos especiales pueden gestionar usuarios</li>
                    <li>Contacta a tu administrador si necesitas acceso</li>
                  </ul>
                </div>
              </div>
            </div>

            <div className="flex gap-3">
              <Button
                variant="secondary"
                leftIcon={<RefreshCw className="w-4 h-4" />}
                onClick={handleRetry}
              >
                Reintentar
              </Button>
              <Button
                variant="primary"
                onClick={() => navigate('/')}
              >
                Volver al Inicio
              </Button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-3xl font-bold text-foreground">Usuarios</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Gestiona los usuarios del sistema
            </p>
          </div>

          <div className="flex gap-2">
            {isAdminOrHigher && (
              <Button
                variant="secondary"
                leftIcon={<ShieldCheck className="w-4 h-4" />}
                onClick={() => navigate('/roles')}
              >
                Gestionar Roles
              </Button>
            )}
            {isAdminOrHigher && (
              <Button
                variant="secondary"
                leftIcon={<KeyRound className="w-4 h-4" />}
                onClick={() => navigate('/permisos')}
              >
                Gestionar Permisos
              </Button>
            )}
            <Button
              variant="primary"
              leftIcon={<Plus className="w-4 h-4" />}
              onClick={() => navigate('/usuarios/nuevo')}
            >
              Nuevo Usuario
            </Button>
          </div>
        </div>

        <div className="flex items-start gap-4">
          <div className="flex-1 min-w-0">
            <StatsGrid
              stats={[
                { icon: <Users className="w-5 h-5" />, label: 'Total', value: globalStats.total, variant: 'default' },
                { icon: <UserCheck className="w-5 h-5" />, label: 'Activos', value: globalStats.total_active, variant: 'success' },
                { icon: <UserX className="w-5 h-5" />, label: 'Inactivos', value: globalStats.total_inactive, variant: 'danger' },
              ]}
            />
          </div>

          {/* Recuadro de filtros activos -- reemplaza a los chips sueltos bajo el buscador */}
          {activeFilterCount > 0 && (
            <div className="flex items-center gap-2 rounded-xl border border-border bg-muted/30 p-2.5 shrink-0 max-w-xl">
              <p className="shrink-0 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Filtros activos
              </p>
              <FilterChips
                groups={filterGroups}
                values={filterValues}
                onRemove={handleRemoveFilterKey}
                direction="row"
              />
            </div>
          )}
        </div>
      </div>

      {/* Contenido principal */}
      {isFirstLoad ? (
        <div
          className="flex items-center justify-center bg-linear-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800 border border-border rounded-xl shadow-xs"
          style={{ minHeight: '550px' }}
        >
          <div className="flex flex-col items-center justify-center">
            <div className="w-12 h-12 border-4 border-brand-500 border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-muted-foreground">Cargando usuarios...</p>
          </div>
        </div>
      ) : users.length === 0 && !isLoading && !searchTerm && estadoFilter === 'all' ? (
        <div className="flex items-center justify-center bg-linear-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800 border border-border rounded-xl shadow-xs" style={{ minHeight: '550px' }}>
          <EmptyState
            icon={<Users className="size-20 text-muted-foreground" strokeWidth={1.5} />}
            title="No hay usuarios registrados"
            description="Comienza a gestionar tu equipo agregando el primer usuario. Podrás asignar roles, permisos y administrar el acceso al sistema."
          />
        </div>
      ) : (
        <div className="space-y-4">
          <TableFilters
            enableSearch
            searchValue={searchTerm}
            onSearchChange={handleSearchChange}
            searchPlaceholder="Buscar por nombre o email..."
            extraFilters={
              <FilterButton
                activeCount={activeFilterCount}
                onOpen={() => setIsFilterModalOpen(true)}
                onClear={handleClearModalFilters}
              />
            }
          />

          <DataTable<User>
            columns={columns}
            data={users}
            actions={actions}
            rowKey="id"
            loading={isLoading}
            emptyMessage="No se encontraron usuarios con los filtros seleccionados"
          />

          <TablePagination
            currentPage={currentPage}
            totalPages={totalPages}
            totalItems={totalItems}
            pageSize={pageSize}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        </div>
      )}

      <ConfirmDialog
        isOpen={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        onConfirm={handleDeleteConfirm}
        title="Eliminar Usuario"
        message={`¿Estás seguro de que deseas eliminar a ${userToDelete?.name || 'este usuario'}? Esta acción no se puede deshacer.`}
        confirmText="Eliminar"
        cancelText="Cancelar"
        variant="danger"
      />

      <FilterModal
        isOpen={isFilterModalOpen}
        onClose={() => setIsFilterModalOpen(false)}
        title="Filtrar usuarios"
        groups={filterGroups}
        values={filterValues}
        onApply={handleApplyModalFilters}
      />
    </div>
  )
}
