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
const EMPTY_ITEMS: StorageQuotaItem[] = []

// Tooltip de capacidad: el valor visible usa la convención base 1024 con etiqueta "GB"
// (decisión de producto); el title aclara la unidad real (GiB) sin cambiar lo que se ve.
function binaryTooltip(bytes: number): string {
  return `${formatBytes(bytes).replace(/ ([KMGT])B$/, ' $1iB')} (base 1024)`
}

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

  // Resultado del último fetch, atado a la clave de la petición que lo produjo: `isLoading`
  // se deriva de que la clave actual todavía no tenga resultado (sin setState síncrono en efectos).
  const [result, setResult] = useState<{
    key: string
    items: StorageQuotaItem[]
    total: number
    totalPages: number
  } | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(PAGE_SIZE)
  // `searchInput` es lo que se ve en el campo (inmediato); `search` es el término ya aplicado (con debounce)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const requestKey = `${page}|${pageSize}|${search}`
  const isLoading = result?.key !== requestKey
  const isFirstLoad = result === null
  // Mientras carga se conservan los datos previos (igual que antes)
  const items = result?.items ?? EMPTY_ITEMS
  const total = result?.total ?? 0
  const totalPages = result?.totalPages ?? 0

  const [capacity, setCapacity] = useState<StorageCapacity | null>(null)

  const [editingQuota, setEditingQuota] = useState<StorageQuotaItem | null>(null)

  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let cancelled = false
    storageQuotaService
      .getQuotas({
        skip: (page - 1) * pageSize,
        limit: pageSize,
        search: search || undefined,
      })
      .then((response) => {
        if (cancelled) return
        setResult({
          key: requestKey,
          items: response.items,
          total: response.total,
          totalPages: response.total_pages,
        })
      })
      .catch(() => {
        if (cancelled) return
        toast.error('Error al cargar las cuotas de almacenamiento')
        setResult((prev) => ({
          key: requestKey,
          items: prev?.items ?? [],
          total: prev?.total ?? 0,
          totalPages: prev?.totalPages ?? 0,
        }))
      })
    return () => {
      cancelled = true
    }
  }, [requestKey, page, pageSize, search])

  useEffect(() => {
    storageQuotaService
      .getCapacity()
      .then(setCapacity)
      .catch(() => setCapacity(null))
  }, [])

  // Al desmontar se cancela el timer pendiente del debounce
  useEffect(() => {
    return () => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    }
  }, [])

  const handleSearchChange = useCallback((value: string) => {
    setSearchInput(value)
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    // Debounce real (300 ms): recién ahí se aplica el término y se vuelve a la página 1
    searchTimerRef.current = setTimeout(() => {
      setSearch(value)
      setPage(1)
    }, 300)
  }, [])

  const handleSaveQuota = useCallback(async (userId: string, limitBytes: number | null) => {
    try {
      const updated = await storageQuotaService.updateQuota(userId, { limit_bytes: limitBytes })
      setResult((prev) =>
        prev ? { ...prev, items: prev.items.map((it) => (it.user_id === userId ? updated : it)) } : prev,
      )
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
      title: capacity?.total_bytes != null ? binaryTooltip(capacity.total_bytes) : undefined,
      variant: 'default' as const,
    },
    {
      icon: <Database className="w-5 h-5" />,
      label: 'Usado',
      value: capacity?.used_bytes != null ? formatBytes(capacity.used_bytes) : 'No disponible',
      title: capacity?.used_bytes != null ? binaryTooltip(capacity.used_bytes) : undefined,
      variant: 'warning' as const,
    },
    {
      icon: <PieChart className="w-5 h-5" />,
      label: 'Libre',
      value: capacity?.free_bytes != null ? formatBytes(capacity.free_bytes) : 'No disponible',
      title: capacity?.free_bytes != null ? binaryTooltip(capacity.free_bytes) : undefined,
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
          searchValue={searchInput}
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
