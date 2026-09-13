import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import {
  Download,
  RefreshCw,
  Activity,
  AlertTriangle,
  Info,
  XCircle,
  Calendar,
  User,
  FileText,
  ScrollText,
  PlusCircle,
  Trash2,
} from 'lucide-react'
import { formatDateTime } from '@/shared/utils/dates'
import { Button } from '@/ui/buttons/Button'
import { Badge } from '@/ui/badges/Badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/ui/tables/Table'
import { Modal } from '@/ui/modals/Modal'
import { TableFilters } from '@/ui/tables/TableFilters'
import { TablePagination } from '@/ui/tables/TablePagination'
import { StatsGrid } from '@/ui/stats/StatsGrid'
import { FilterButton, FilterModal, FilterChips, countActiveFilters, type FilterGroup, type FilterValues } from '@/ui/filters'
import { auditLogService } from '../services/auditLog.service'
import type { AuditLog, AuditLogDetail, AuditStats } from '../services/auditLog.service'
import { toast } from 'sonner'

// ===========================
// Tipos locales
// ===========================

type LogLevel = 'info' | 'warning' | 'error' | 'success'

interface LogEntry {
  id: string
  timestamp: string
  level: LogLevel
  user: string
  action: string
  module: string
  ip_address: string
  details: string
  metadata?: Record<string, unknown>
}

// ===========================
// Helpers
// ===========================

const mapActionToLevel = (action: string): LogLevel => {
  switch (action.toUpperCase()) {
    case 'CREATE': return 'success'
    case 'UPDATE': return 'info'
    case 'DELETE': return 'warning'
    default:       return 'info'
  }
}

const mapAuditLogToEntry = (log: AuditLog): LogEntry => ({
  id: log.id.toString(),
  timestamp: log.created_at,
  level: mapActionToLevel(log.action),
  user: log.user_email,
  action: `${log.action} en ${log.table_name}`,
  module: log.table_name,
  ip_address: log.ip_address || '—',
  details: `${log.method} ${log.endpoint}`,
  metadata: {
    record_id: log.record_id,
    user_id: log.user_id,
    endpoint: log.endpoint,
    method: log.method,
  },
})

// "2026-08-28" -> instante ISO en el límite del día (hora local del navegador),
// igual criterio que usaba el filtro de período anterior con los presets fijos.
// `dayOffset` 0 = medianoche de ese día (límite inferior), 1 = medianoche del
// día siguiente (límite superior, ya que el backend filtra created_at <= end_date).
function dateBoundaryISO(dateStr: string, dayOffset: 0 | 1): string {
  const [y, m, d] = dateStr.split('-').map(Number)
  return new Date(y, m - 1, d + dayOffset).toISOString()
}

// Fecha local de hoy en formato "yyyy-mm-dd" (el mismo que usa el input type="date"
// de DateRangeField). Se usa como default de `dateFrom` al montar la página --
// preserva el comportamiento que tenía el filtro de período anterior, que arrancaba
// en el preset "Hoy" (getDateRange('hoy') acotaba a start_date = medianoche local,
// sin end_date). El usuario puede quitarlo o cambiarlo desde el modal.
function todayDateStr(): string {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const LEVEL_COLORS: Record<string, string> = {
  info:    'bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-400',
  success: 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400',
  warning: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400',
  error:   'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400',
}

const LEVEL_ICONS: Record<string, React.ReactNode> = {
  info:    <Info className="h-3.5 w-3.5" />,
  success: <Activity className="h-3.5 w-3.5" />,
  warning: <AlertTriangle className="h-3.5 w-3.5" />,
  error:   <XCircle className="h-3.5 w-3.5" />,
}

// ===========================
// Componente
// ===========================

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null)
  const [selectedLogDetail, setSelectedLogDetail] = useState<AuditLogDetail | null>(null)
  const [isDetailOpen, setIsDetailOpen] = useState(false)
  const [total, setTotal] = useState(0)
  const [availableModules, setAvailableModules] = useState<string[]>([])
  const [isFilterModalOpen, setIsFilterModalOpen] = useState(false)

  // Paginación real (antes: limit fijo en 50, sin controles) -- mismo patrón que ProductosPage.
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  // Stats globales (sin filtrar) para la fila de StatsGrid del header -- mismo
  // patrón que ProductosPage: se cargan una sola vez, independientes del filtro activo.
  const [stats, setStats] = useState<AuditStats>({ total_logs: 0, by_action: {}, top_tables: [] })

  // ---- Filtros "Tipo de acción", "Período" y "Módulo" vía el modal reutilizable ----
  // (filemeshy_front/src/ui/filters). Reemplaza el sidebar fijo con tabs + selects que
  // tenía esta página antes -- ahora vive todo adentro del modal, igual que el
  // resto de las vistas. El buscador (usuario/endpoint) queda fuera, independiente.
  const [actionFilter, setActionFilter] = useState<string>('')
  // Default "Hoy" (mismo comportamiento que el preset por defecto anterior) -- ver todayDateStr().
  const [dateFrom, setDateFrom] = useState<string>(() => todayDateStr())
  const [dateTo, setDateTo] = useState<string>('')
  const [moduleFilter, setModuleFilter] = useState<string>('')

  const filterGroups: FilterGroup[] = useMemo(() => [
    {
      title: 'Tipo de acción',
      fields: [
        {
          key: 'action',
          label: 'Tipo de acción',
          shortLabel: 'Acción',
          type: 'select',
          placeholder: 'Todas',
          options: [
            { value: 'CREATE', label: 'Creaciones' },
            { value: 'UPDATE', label: 'Actualizaciones' },
            { value: 'DELETE', label: 'Eliminaciones' },
          ],
        },
      ],
    },
    {
      title: 'Período',
      fields: [
        {
          key: 'start_date',
          label: 'Fecha del registro',
          shortLabel: 'Fecha',
          type: 'dateRange',
          fromKey: 'start_date',
          toKey: 'end_date',
        },
      ],
    },
    {
      title: 'Módulo',
      fields: [
        {
          key: 'table_name',
          label: 'Módulo / tabla afectada',
          shortLabel: 'Módulo',
          type: 'select',
          placeholder: 'Todos',
          options: availableModules.map((mod) => ({ value: mod, label: mod })),
        },
      ],
    },
  ], [availableModules])

  const filterValues: FilterValues = useMemo(() => ({
    action: actionFilter || undefined,
    start_date: dateFrom || undefined,
    end_date: dateTo || undefined,
    table_name: moduleFilter || undefined,
  }), [actionFilter, dateFrom, dateTo, moduleFilter])

  const activeFilterCount = useMemo(
    () => countActiveFilters(filterGroups, filterValues),
    [filterGroups, filterValues]
  )

  const handleApplyModalFilters = useCallback((newValues: FilterValues) => {
    setActionFilter((newValues.action as string | undefined) ?? '')
    setDateFrom((newValues.start_date as string | undefined) ?? '')
    setDateTo((newValues.end_date as string | undefined) ?? '')
    setModuleFilter((newValues.table_name as string | undefined) ?? '')
    setCurrentPage(1)
  }, [])

  const handleClearModalFilters = useCallback(() => {
    handleApplyModalFilters({})
  }, [handleApplyModalFilters])

  const handlePageSizeChange = useCallback((size: number) => {
    setPageSize(size)
    setCurrentPage(1)
  }, [])

  // Quitar un chip individual: cada filtro limpia solo su(s) propia(s) clave(s),
  // preservando el resto (el rango de fecha limpia start_date y end_date juntos).
  const handleRemoveFilterKey = useCallback((key: string) => {
    const current: FilterValues = {
      action: actionFilter || undefined,
      start_date: dateFrom || undefined,
      end_date: dateTo || undefined,
      table_name: moduleFilter || undefined,
    }
    if (key === 'start_date' || key === 'end_date') {
      handleApplyModalFilters({ ...current, start_date: undefined, end_date: undefined })
      return
    }
    handleApplyModalFilters({ ...current, [key]: undefined })
  }, [actionFilter, dateFrom, dateTo, moduleFilter, handleApplyModalFilters])

  // Debounce SOLO para búsqueda por teclado (300ms) -- mismo patrón que ProductosPage.
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const handleSearchChange = useCallback((value: string) => {
    setSearchTerm(value)
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => {
      setDebouncedSearch(value)
      setCurrentPage(1)
    }, 300)
  }, [])

  const loadLogs = useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await auditLogService.getLogs({
        action: actionFilter || undefined,
        table_name: moduleFilter || undefined,
        start_date: dateFrom ? dateBoundaryISO(dateFrom, 0) : undefined,
        end_date: dateTo ? dateBoundaryISO(dateTo, 1) : undefined,
        search: debouncedSearch || undefined,
        skip: (currentPage - 1) * pageSize,
        limit: pageSize,
      })

      setLogs(data.logs.map(mapAuditLogToEntry))
      setTotal(data.total)
      const modules = [...new Set(data.logs.map((l: AuditLog) => l.table_name))].filter(Boolean).sort() as string[]
      setAvailableModules(modules)
    } catch {
      toast.error('Error al cargar los logs de auditoría')
    } finally {
      setIsLoading(false)
    }
  }, [actionFilter, dateFrom, dateTo, moduleFilter, debouncedSearch, currentPage, pageSize])

  useEffect(() => { loadLogs() }, [actionFilter, dateFrom, dateTo, moduleFilter, debouncedSearch, currentPage, pageSize])

  // Stats globales una sola vez al montar.
  useEffect(() => {
    auditLogService.getStats().then(setStats).catch(() => {
      // Sin stats no rompe la página -- StatsGrid simplemente muestra 0
    })
  }, [])

  const handleOpenDetail = async (log: LogEntry) => {
    setSelectedLog(log)
    setSelectedLogDetail(null)
    setIsDetailOpen(true)
    try {
      const detail = await auditLogService.getLogDetail(log.id)
      setSelectedLogDetail(detail)
    } catch {
      // Muestra info básica si falla el detalle
    }
  }

  const handleExportLogs = () => {
    if (logs.length === 0) { toast.info('No hay logs para exportar'); return }
    const headers = ['ID', 'Fecha/Hora', 'Tipo', 'Usuario', 'Acción', 'Módulo', 'IP', 'Endpoint']
    const rows = logs.map(l => [l.id, formatDateTime(l.timestamp) ?? '', l.level, l.user, l.action, l.module, l.ip_address, l.details])
    const csv = [headers, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `logs-auditoria-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
    toast.success('Logs exportados correctamente')
  }

  return (
    <div className="space-y-6">
      {/* Header -- mismo patrón que ProductosPage: h1 + subtítulo, botones a la derecha */}
      <div className="mb-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-3xl font-bold text-foreground">Logs de Auditoría</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Registro de actividades del sistema
              {total > 0 && <span> · {total.toLocaleString('es-DO')} con los filtros actuales</span>}
            </p>
          </div>

          <div className="flex gap-2">
            <Button variant="secondary" onClick={loadLogs} leftIcon={<RefreshCw className="w-4 h-4" />}>
              Actualizar
            </Button>
            <Button variant="secondary" onClick={handleExportLogs} leftIcon={<Download className="w-4 h-4" />}>
              Exportar CSV
            </Button>
          </div>
        </div>

        <div className="flex items-start gap-4">
          <div className="flex-1 min-w-0">
            <StatsGrid
              stats={[
                { icon: <ScrollText className="w-5 h-5" />, label: 'Total', value: stats.total_logs, variant: 'default' },
                { icon: <PlusCircle className="w-5 h-5" />, label: 'Creaciones', value: stats.by_action.CREATE ?? 0, variant: 'success' },
                { icon: <Info className="w-5 h-5" />, label: 'Actualizaciones', value: stats.by_action.UPDATE ?? 0, variant: 'info' },
                { icon: <Trash2 className="w-5 h-5" />, label: 'Eliminaciones', value: stats.by_action.DELETE ?? 0, variant: 'danger' },
              ]}
            />
          </div>

          {/* Recuadro de filtros activos -- mismo patrón que FacturasPage/ProductosPage */}
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

      <div className="space-y-4">
        {/* Búsqueda + filtro -- mismo componente TableFilters que el resto de las vistas */}
        <TableFilters
          enableSearch
          searchValue={searchTerm}
          onSearchChange={handleSearchChange}
          searchPlaceholder="Buscar por usuario, endpoint..."
          extraFilters={
            <FilterButton
              activeCount={activeFilterCount}
              onOpen={() => setIsFilterModalOpen(true)}
              onClear={handleClearModalFilters}
            />
          }
        />

        {/* Tabla */}
        <div className="bg-card border border-border rounded-2xl overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Fecha/Hora</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Usuario</TableHead>
                <TableHead>Módulo</TableHead>
                <TableHead>Acción</TableHead>
                <TableHead>IP</TableHead>
                <TableHead className="text-right">Ver</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-12 text-muted-foreground">
                    Cargando logs...
                  </TableCell>
                </TableRow>
              ) : logs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-12 text-muted-foreground">
                    No se encontraron registros
                  </TableCell>
                </TableRow>
              ) : (
                logs.map((log) => (
                  <TableRow key={log.id}>
                    <TableCell className="text-sm">
                      <div className="flex items-center gap-1.5 text-muted-foreground">
                        <Calendar className="h-3.5 w-3.5 shrink-0" />
                        {formatDateTime(log.timestamp)}
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${LEVEL_COLORS[log.level] ?? 'bg-muted text-muted-foreground'}`}>
                        {LEVEL_ICONS[log.level]}
                        {log.level}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        <User className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <span className="text-sm font-medium">{log.user}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="gray">{log.module}</Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{log.action}</TableCell>
                    <TableCell className="text-sm text-muted-foreground font-mono">{log.ip_address}</TableCell>
                    <TableCell className="text-right">
                      <Button size="sm" variant="ghost" onClick={() => handleOpenDetail(log)}>
                        <FileText className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        {/* Paginación (solo si >50 registros) -- mismo patrón que ProductosPage */}
        <TablePagination
          currentPage={currentPage}
          totalPages={totalPages}
          totalItems={total}
          pageSize={pageSize}
          onPageChange={setCurrentPage}
          onPageSizeChange={handlePageSizeChange}
        />
      </div>

      {/* Modal detalle */}
      <Modal isOpen={isDetailOpen} onClose={() => setIsDetailOpen(false)} title="Detalle del registro" size="2xl">
        {selectedLog && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">Fecha/Hora</p>
                <p className="text-sm text-foreground">{formatDateTime(selectedLog.timestamp) ?? ''}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">Tipo</p>
                <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${LEVEL_COLORS[selectedLog.level]}`}>
                  {LEVEL_ICONS[selectedLog.level]}
                  {selectedLog.level}
                </span>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">Usuario</p>
                <p className="text-sm font-semibold text-foreground">{selectedLog.user}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">Módulo</p>
                <p className="text-sm text-foreground">{selectedLog.module}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">Dirección IP</p>
                <p className="text-sm font-mono text-foreground">{selectedLog.ip_address}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">ID Registro</p>
                <p className="text-sm text-foreground">{(selectedLog.metadata?.record_id as string) || '—'}</p>
              </div>
            </div>

            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">Acción</p>
              <p className="text-sm font-semibold text-foreground">{selectedLog.action}</p>
            </div>

            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">Endpoint</p>
              <div className="bg-muted rounded-lg px-3 py-2">
                <code className="text-sm text-foreground">{selectedLog.details}</code>
              </div>
            </div>

            {selectedLogDetail?.changes && Object.keys(selectedLogDetail.changes).length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-2">Cambios realizados</p>
                <pre className="bg-gray-900 text-green-400 p-4 rounded-xl overflow-x-auto text-xs">
                  {JSON.stringify(selectedLogDetail.changes, null, 2)}
                </pre>
              </div>
            )}

            {selectedLogDetail?.old_data && (
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-2">Datos anteriores</p>
                <pre className="bg-gray-900 text-yellow-300 p-4 rounded-xl overflow-x-auto text-xs">
                  {JSON.stringify(selectedLogDetail.old_data, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </Modal>

      <FilterModal
        isOpen={isFilterModalOpen}
        onClose={() => setIsFilterModalOpen(false)}
        title="Filtrar logs"
        groups={filterGroups}
        values={filterValues}
        onApply={handleApplyModalFilters}
      />
    </div>
  )
}
