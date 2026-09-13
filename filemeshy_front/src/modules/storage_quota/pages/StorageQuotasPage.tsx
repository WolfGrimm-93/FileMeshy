/**
 * PÁGINA: CUOTAS DE ALMACENAMIENTO
 * Administración del límite de almacenamiento por usuario + capacidad real de disco
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { HardDrive, Database, PieChart } from 'lucide-react'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import { Permission } from '@/app/routes'
import { DataTable, type Column, type TableAction } from '@/ui/tables/DataTable'
import { TableFilters } from '@/ui/tables/TableFilters'
import { TablePagination } from '@/ui/tables/TablePagination'
import { StatsGrid } from '@/ui/stats/StatsGrid'
import { toast } from '@/ui/toast/CustomToast'
import { formatBytes } from '@/shared/utils/downloadFile'
import { storageQuotaService, type StorageQuotaItem, type StorageCapacity } from '../services/storage-quota.service'
import { EditQuotaModal } from '../components/EditQuotaModal'

const PAGE_SIZE = 50

// Umbrales de color de la barra de consumo -- reusa los mismos tokens
// semánticos (verde/amarillo/rojo) que ya usa Badge/StatsGrid en el resto
// de la app para success/warning/danger, en vez de inventar una paleta nueva.
function usageBarColor(pct: number): string {
  if (pct >= 90) return 'bg-red-500'
  if (pct >= 70) return 'bg-yellow-500'
  return 'bg-green-500'
}

function UsageCell({ item }: { item: StorageQuotaItem }) {
  const pct = item.limit_bytes ? Math.min(100, (item.bytes_used / item.limit_bytes) * 100) : null

  return (
    <div className="min-w-[140px]">
      <span className="text-sm">{formatBytes(item.bytes_used)}</span>
      {pct !== null && (
        <div className="mt-1 h-1.5 w-full rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${usageBarColor(pct)}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  )
}

export default function StorageQuotasPage() {
  const { hasPermission } = useAuth()
  const canManage = hasPermission(Permission.MANAGE_STORAGE_QUOTAS)

  const [items, setItems] = useState<StorageQuotaItem[]>([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(PAGE_SIZE)
  const [search, setSearch] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isFirstLoad, setIsFirstLoad] = useState(true)

  const [capacity, setCapacity] = useState<StorageCapacity | null>(null)

  const [editingQuota, setEditingQuota] = useState<StorageQuotaItem | null>(null)

  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchQuotas = useCallback(async () => {
    setIsLoading(true)
    try {
      const skip = (page - 1) * pageSize
      const response = await storageQuotaService.getQuotas({
        skip,
        limit: pageSize,
        search: search || undefined,
      })
      setItems(response.items)
      setTotal(response.total)
      setTotalPages(response.total_pages)
    } catch {
      toast.error('Error al cargar las cuotas de almacenamiento')
    } finally {
      setIsLoading(false)
      setIsFirstLoad(false)
    }
  }, [page, pageSize, search])

  useEffect(() => {
    fetchQuotas()
  }, [fetchQuotas])

  useEffect(() => {
    storageQuotaService
      .getCapacity()
      .then(setCapacity)
      .catch(() => setCapacity(null))
  }, [])

  const handleSearchChange = useCallback((value: string) => {
    setSearch(value)
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => setPage(1), 300)
  }, [])

  const handleSaveQuota = useCallback(async (userId: string, limitBytes: number | null) => {
    try {
      const updated = await storageQuotaService.updateQuota(userId, { limit_bytes: limitBytes })
      setItems((prev) => prev.map((it) => (it.user_id === userId ? updated : it)))
      toast.success('Cuota actualizada exitosamente')
    } catch {
      toast.error('Error al actualizar la cuota')
      throw new Error('update-quota-failed')
    }
  }, [])

  const columns: Column<StorageQuotaItem>[] = useMemo(() => [
    {
      key: 'first_name',
      label: 'Usuario',
      render: (_value, row) => (
        <div>
          <p className="text-sm font-medium">{row.first_name} {row.last_name}</p>
          <p className="text-xs text-muted-foreground">{row.email}</p>
        </div>
      ),
    },
    {
      key: 'limit_bytes',
      label: 'Cuota asignada',
      width: '160px',
      render: (value) => (
        <span className="text-sm">{value === null ? 'Sin límite' : formatBytes(value as number)}</span>
      ),
    },
    {
      key: 'bytes_used',
      label: 'Consumo',
      width: '180px',
      render: (_value, row) => <UsageCell item={row} />,
    },
  ], [])

  const actions: TableAction<StorageQuotaItem>[] = useMemo(() => {
    if (!canManage) return []
    return [
      {
        icon: 'edit',
        label: 'Editar cuota',
        onClick: (row) => setEditingQuota(row),
      },
    ]
  }, [canManage])

  // Capacidad real de disco -- "No disponible" si el backend no pudo leerla
  // (viene todo en null) en vez de romper la pantalla o mostrar NaN/null.
  const capacityStats = [
    {
      icon: <HardDrive className="w-5 h-5" />,
      label: 'Capacidad total',
      value: capacity?.total_bytes != null ? formatBytes(capacity.total_bytes) : 'No disponible',
      variant: 'default' as const,
    },
    {
      icon: <Database className="w-5 h-5" />,
      label: 'Usado',
      value: capacity?.used_bytes != null ? formatBytes(capacity.used_bytes) : 'No disponible',
      variant: 'warning' as const,
    },
    {
      icon: <PieChart className="w-5 h-5" />,
      label: 'Libre',
      value: capacity?.free_bytes != null ? formatBytes(capacity.free_bytes) : 'No disponible',
      variant: 'success' as const,
    },
  ]

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-foreground">Cuotas de Almacenamiento</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Administrá el límite de almacenamiento asignado a cada usuario
        </p>
      </div>

      <StatsGrid stats={capacityStats} />

      <div className="space-y-4">
        <TableFilters
          enableSearch
          searchValue={search}
          onSearchChange={handleSearchChange}
          searchPlaceholder="Buscar por nombre o email..."
        />

        <DataTable<StorageQuotaItem>
          columns={columns}
          data={items}
          actions={actions}
          rowKey="user_id"
          loading={isLoading && !isFirstLoad}
          emptyMessage="No se encontraron usuarios con los filtros seleccionados"
        />

        <TablePagination
          currentPage={page}
          totalPages={totalPages}
          totalItems={total}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={(size) => { setPageSize(size); setPage(1) }}
        />
      </div>

      <EditQuotaModal
        isOpen={editingQuota !== null}
        onClose={() => setEditingQuota(null)}
        quota={editingQuota}
        onSave={handleSaveQuota}
      />
    </div>
  )
}
