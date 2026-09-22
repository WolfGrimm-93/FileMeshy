/**
 * PÁGINA: TENANTS (panel de plataforma)
 *
 * Alta y activación/desactivación de tenants -- ve TODOS los tenants de la
 * instalación, por eso vive fuera del RBAC normal (ver contrato de la
 * Ronda 8 / guards/PlatformAuthGuard.tsx). Reusa el mismo patrón de
 * DataTable que StorageQuotasPage/BackupsPage.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Building2, Loader2, LogOut, Plus, RefreshCw } from 'lucide-react'
import { DataTable, type Column, type TableAction } from '@/ui/tables/DataTable'
import { Button } from '@/ui/buttons/Button'
import { Badge } from '@/ui/badges/Badge'
import { EmptyState } from '@/ui/empty-states/EmptyState'
import { ConfirmDialog } from '@/ui/modals/ConfirmDialog'
import { toast } from '@/ui/toast/CustomToast'
import { usePlatformAuthStore } from '../store/platformAuthStore'
import {
  tenantsService,
  type TenantListItem,
  type TenantCreatePayload,
  type TenantCreateResult,
} from '../services/tenants.service'
import { getPlatformErrorMessage } from '../services/platformAdmin.api'
import { CreateTenantModal } from '../components/CreateTenantModal'
import { TenantCredentialsModal } from '../components/TenantCredentialsModal'

// Formateo de "creado" sin depender de shared/utils/dates (módulo
// deliberadamente desacoplado del resto de la app) -- formato simple
// suficiente para un panel de operador.
function formatCreatedAt(isoString: string): string {
  const date = new Date(isoString)
  if (isNaN(date.getTime())) return isoString
  return date.toLocaleString('es-DO', { dateStyle: 'medium', timeStyle: 'short' })
}

export default function PlatformTenantsPage() {
  const navigate = useNavigate()
  const clearKey = usePlatformAuthStore((s) => s.clearKey)

  const [tenants, setTenants] = useState<TenantListItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isFirstLoad, setIsFirstLoad] = useState(true)
  // Separado de `tenants.length === 0` a propósito: un 500 del backend y una
  // lista realmente vacía renderizaban el mismo EmptyState "Todavía no hay
  // tenants" (confirmado con Playwright -- pixel-idénticos, la única señal
  // era un toast que desaparece a los 3s). Con este flag muestran mensajes
  // distintos.
  const [hasError, setHasError] = useState(false)

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [createdResult, setCreatedResult] = useState<TenantCreateResult | null>(null)
  const [toggleTarget, setToggleTarget] = useState<TenantListItem | null>(null)
  // Id del tenant cuyo PATCH de activar/desactivar está en vuelo (no un
  // booleano global: solo esa fila puntual queda "ocupada"). Reemplaza al
  // viejo guard `isToggling` en el `onClose` de ConfirmDialog -- ese guard
  // no cumplía ninguna función (ConfirmDialog cierra sincrónicamente apenas
  // se confirma, antes de que el `setState` de más abajo llegue a reflejarse
  // en ese closure) y quedaba como ruido engañoso. Acá se usa en cambio para
  // ocultar el botón de esa fila mientras el PATCH está en curso (evita
  // doble click) y para mostrar un spinner puntual en su badge de Estado.
  const [togglingId, setTogglingId] = useState<string | null>(null)

  const fetchTenants = useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await tenantsService.list()
      setTenants(data)
      setHasError(false)
    } catch (err) {
      setHasError(true)
      toast.error(getPlatformErrorMessage(err, 'Error al cargar los tenants'))
    } finally {
      setIsLoading(false)
      setIsFirstLoad(false)
    }
  }, [])

  useEffect(() => {
    fetchTenants()
  }, [fetchTenants])

  const handleLogout = useCallback(() => {
    clearKey()
    navigate('/plataforma/login')
  }, [clearKey, navigate])

  const handleCreate = useCallback(async (payload: TenantCreatePayload) => {
    try {
      const result = await tenantsService.create(payload)
      setIsCreateOpen(false)
      setCreatedResult(result)
      toast.success('Tenant creado exitosamente')
      fetchTenants()
    } catch (err) {
      toast.error(getPlatformErrorMessage(err, 'Error al crear el tenant'))
      // No relanzar -- el modal ya queda abierto para que el operador corrija
      // y reintente, el toast ya comunicó el detalle del error del backend.
    }
  }, [fetchTenants])

  const handleConfirmToggle = useCallback(async () => {
    if (!toggleTarget) return
    // Copia local -- ConfirmDialog ya limpió `toggleTarget` (cierra
    // sincrónicamente al confirmar, ver comentario del estado de arriba)
    // para cuando esta función siga corriendo después del primer `await`.
    const target = toggleTarget
    setTogglingId(target.id)
    try {
      const updated = await tenantsService.update(target.id, { is_active: !target.is_active })
      setTenants((prev) => prev.map((t) => (t.id === updated.id ? updated : t)))
      toast.success(updated.is_active ? 'Tenant activado' : 'Tenant desactivado')
    } catch (err) {
      toast.error(getPlatformErrorMessage(err, 'Error al actualizar el tenant'))
    } finally {
      setTogglingId(null)
    }
  }, [toggleTarget])

  const columns: Column<TenantListItem>[] = useMemo(() => [
    {
      key: 'slug',
      label: 'Slug',
      render: (value) => <span className="font-mono text-sm">{value as string}</span>,
    },
    {
      key: 'company_name',
      label: 'Empresa',
    },
    {
      key: 'plan',
      label: 'Plan',
      width: '120px',
      render: (value) => <Badge variant="info" style="soft">{value as string}</Badge>,
    },
    {
      key: 'is_active',
      label: 'Estado',
      width: '150px',
      render: (value, row) => (
        <div className="flex items-center gap-2">
          <Badge variant={value ? 'success' : 'gray'} style="soft">
            {value ? 'Activo' : 'Inactivo'}
          </Badge>
          {row.id === togglingId && (
            <Loader2 className="size-3.5 animate-spin text-muted-foreground" aria-label="Actualizando" />
          )}
        </div>
      ),
    },
    {
      key: 'created_at',
      label: 'Creado',
      width: '200px',
      render: (value) => <span className="text-sm text-muted-foreground">{formatCreatedAt(value as string)}</span>,
    },
    // togglingId es dependencia real: se lee dentro del render de la columna
    // Estado de arriba (spinner puntual de la fila en curso).
  ], [togglingId])

  const actions: TableAction<TenantListItem>[] = useMemo(() => [
    {
      icon: 'activate',
      label: 'Activar',
      // También oculto mientras el PATCH de esa fila está en vuelo -- evita
      // doble click sin tocar DataTable/ConfirmDialog (compartidos, fuera de
      // alcance de este fix).
      hidden: (row) => row.is_active || row.id === togglingId,
      onClick: (row) => setToggleTarget(row),
    },
    {
      icon: 'deactivate',
      label: 'Desactivar',
      hidden: (row) => !row.is_active || row.id === togglingId,
      onClick: (row) => setToggleTarget(row),
    },
  ], [togglingId])

  return (
    <div className="min-h-screen bg-gray-50 p-6 dark:bg-gray-950 sm:p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-foreground">Tenants</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Panel de plataforma -- alta y activación de tenants (modo cloud)
            </p>
          </div>

          <div className="flex shrink-0 gap-2">
            <Button variant="secondary" onClick={fetchTenants} leftIcon={<RefreshCw className="w-4 h-4" />}>
              Actualizar
            </Button>
            <Button variant="primary" onClick={() => setIsCreateOpen(true)} leftIcon={<Plus className="w-4 h-4" />}>
              Crear tenant
            </Button>
            <Button variant="ghost" onClick={handleLogout} leftIcon={<LogOut className="w-4 h-4" />}>
              Salir
            </Button>
          </div>
        </div>

        {isFirstLoad ? (
          // Carga inicial -- antes se caía directo a la rama del DataTable
          // con `tenants` todavía vacío, así que se veía un flash de "No se
          // encontraron tenants" antes de que llegara la respuesta (el
          // overlay de `loading` del DataTable estaba apagado a propósito
          // en el primer fetch para no chocar con el EmptyState de abajo,
          // pero eso dejaba este hueco). Ahora el primer fetch tiene su
          // propio estado explícito, sin flash.
          <div className="flex justify-center py-12">
            <div className="size-8 animate-spin rounded-full border-3 border-brand-500 border-t-transparent" />
          </div>
        ) : hasError ? (
          // Separado de "lista vacía" a propósito -- un 500 del backend y
          // una lista realmente vacía se veían pixel-idénticos (mismo
          // EmptyState), la única señal era un toast que desaparece a los 3s.
          <div className="flex justify-center py-12">
            <EmptyState
              icon={<AlertTriangle className="size-full" />}
              title="No se pudo cargar"
              description="Ocurrió un error al obtener la lista de tenants. Probá de nuevo."
              primaryAction={{ label: 'Reintentar', onClick: fetchTenants }}
            />
          </div>
        ) : tenants.length === 0 ? (
          <div className="flex justify-center py-12">
            <EmptyState
              icon={<Building2 className="size-full" />}
              title="Todavía no hay tenants"
              description="Cuando se cree un tenant nuevo, va a aparecer en esta lista."
              primaryAction={{ label: 'Crear tenant', onClick: () => setIsCreateOpen(true) }}
            />
          </div>
        ) : (
          <DataTable<TenantListItem>
            columns={columns}
            data={tenants}
            actions={actions}
            rowKey="id"
            loading={isLoading}
            emptyMessage="No se encontraron tenants"
          />
        )}
      </div>

      <CreateTenantModal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSubmit={handleCreate}
      />

      <TenantCredentialsModal
        result={createdResult}
        onClose={() => setCreatedResult(null)}
      />

      <ConfirmDialog
        isOpen={toggleTarget !== null}
        onClose={() => setToggleTarget(null)}
        onConfirm={handleConfirmToggle}
        title={toggleTarget?.is_active ? 'Desactivar tenant' : 'Activar tenant'}
        message={
          toggleTarget
            ? `¿Confirmás que querés ${toggleTarget.is_active ? 'desactivar' : 'activar'} el tenant "${toggleTarget.company_name}" (${toggleTarget.slug})?`
            : ''
        }
        variant={toggleTarget?.is_active ? 'danger' : 'success'}
        confirmText={toggleTarget?.is_active ? 'Desactivar' : 'Activar'}
      />
    </div>
  )
}
