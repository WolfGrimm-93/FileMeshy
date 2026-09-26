/**
 * PÁGINA: COPIAS DE SEGURIDAD
 * Administración de backups automáticos de Postgres y MinIO -- historial +
 * disparo manual. Solo lectura + una acción (correr backup ahora); sin
 * paginación porque el backend no la define en el contrato de Ronda 7.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Database, Box, CheckCircle2, XCircle, Loader2, Info, RefreshCw, PlayCircle } from 'lucide-react'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import { Permission } from '@/app/routes'
import { DataTable, type Column } from '@/ui/tables/DataTable'
import { Button } from '@/ui/buttons/Button'
import { Badge, type BadgeVariant } from '@/ui/badges/Badge'
import { EmptyState } from '@/ui/empty-states/EmptyState'
import { Modal } from '@/ui/modals/Modal'
import { toast } from '@/ui/toast/CustomToast'
import { formatDateTime, parseDate } from '@/shared/utils/dates'
import { formatBytes } from '@/shared/utils/downloadFile'
import { backupsService, type BackupRun, type BackupType } from '../services/backups.service'

// Tiempo de espera antes de refrescar el listado automáticamente después de
// disparar un backup manual. El backup real puede tardar más, pero para
// entonces ya debería existir la fila "En curso" -- si no aparece, el botón
// "Actualizar" manual de la tabla permite reintentar sin esperar de nuevo.
const AUTO_REFRESH_DELAY_MS = 4000

// Si el error de un backup de MinIO fallido menciona esto, se interpreta como
// una limitación de configuración conocida (MinIO no configurado en esta
// instalación) y no como una falla real del sistema -- se muestra en un tono
// informativo/gris en vez de rojo de alarma.
//
// NOTA PARA REVISIÓN ADVERSARIAL: este substring es una suposición sobre el
// mensaje exacto que va a mandar el backend (en construcción en paralelo). Si
// el backend usa otra redacción, esta fila cae en la rama roja de "falla
// real" por defecto -- ajustar este substring (o pedirle al backend un campo
// explícito, ej. `error_code: 'not_configured'`) en la próxima ronda.
const MINIO_NOT_CONFIGURED_HINT = 'no configurado'

const TYPE_CONFIG: Record<BackupType, { label: string; icon: typeof Database; variant: BadgeVariant }> = {
  postgres: { label: 'Postgres', icon: Database, variant: 'info' },
  minio: { label: 'MinIO', icon: Box, variant: 'purple' },
}

type RowTone = 'success' | 'failed' | 'running' | 'notConfigured'

function rowTone(run: BackupRun): RowTone {
  if (run.status === 'running') return 'running'
  if (run.status === 'success') return 'success'
  // status === 'failed'
  if (run.backup_type === 'minio' && (run.error_message || '').toLowerCase().includes(MINIO_NOT_CONFIGURED_HINT)) {
    return 'notConfigured'
  }
  return 'failed'
}

function StatusBadgeCell({ run }: { run: BackupRun }) {
  const tone = rowTone(run)

  const config: Record<RowTone, { variant: BadgeVariant; label: string; icon: React.ReactNode }> = {
    success: { variant: 'success', label: 'Éxito', icon: <CheckCircle2 className="h-3.5 w-3.5" /> },
    failed: { variant: 'danger', label: 'Falló', icon: <XCircle className="h-3.5 w-3.5" /> },
    running: { variant: 'warning', label: 'En curso', icon: <Loader2 className="h-3.5 w-3.5 animate-spin" /> },
    notConfigured: { variant: 'gray', label: 'No configurado', icon: <Info className="h-3.5 w-3.5" /> },
  }

  const { variant, label, icon } = config[tone]
  return <Badge variant={variant} icon={icon}>{label}</Badge>
}

// Duración legible entre started_at y finished_at. Sin finished_at (backup
// todavía corriendo) muestra "En curso" en vez de un cálculo sin sentido.
function formatDuration(startedAt: string, finishedAt: string | null): string {
  if (!finishedAt) return 'En curso'

  const startDate = parseDate(startedAt)
  const endDate = parseDate(finishedAt)
  if (!startDate || !endDate) return '—'
  const start = startDate.getTime()
  const end = endDate.getTime()
  if (end < start) return '—'

  const totalSeconds = Math.round((end - start) / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60

  if (minutes === 0) return `${seconds}s`
  return `${minutes}m ${seconds}s`
}

const ERROR_PREVIEW_LENGTH = 80

export default function BackupsPage() {
  const { hasPermission } = useAuth()
  // backups.view es el único permiso relevante para ambos endpoints (listar
  // y disparar) -- no hay un permiso "manage" separado del lado backend.
  const canManage = hasPermission(Permission.VIEW_BACKUPS)

  const [runs, setRuns] = useState<BackupRun[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isFirstLoad, setIsFirstLoad] = useState(true)
  const [isRunningBackup, setIsRunningBackup] = useState(false)
  const [errorDetail, setErrorDetail] = useState<BackupRun | null>(null)

  const autoRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Núcleo del fetch (sin setState síncrono; `isLoading` arranca en true)
  const fetchRuns = useCallback(
    () =>
      backupsService
        .list()
        .then((data) => {
          setRuns(data)
        })
        .catch(() => {
          toast.error('Error al cargar el historial de backups')
        })
        .finally(() => {
          setIsLoading(false)
          setIsFirstLoad(false)
        }),
    []
  )

  // Refresco explícito (botón, timer tras disparar un backup): muestra el loading
  const refreshRuns = useCallback(() => {
    setIsLoading(true)
    return fetchRuns()
  }, [fetchRuns])

  useEffect(() => {
    fetchRuns()
    return () => {
      if (autoRefreshTimerRef.current) clearTimeout(autoRefreshTimerRef.current)
    }
  }, [fetchRuns])

  const handleRunNow = useCallback(async () => {
    setIsRunningBackup(true)
    try {
      const response = await backupsService.runNow()
      const fallbackMessage = 'Backup encolado, va a aparecer en la lista en unos segundos'
      if (response.queued) {
        toast.success(response.message || fallbackMessage)
        if (autoRefreshTimerRef.current) clearTimeout(autoRefreshTimerRef.current)
        autoRefreshTimerRef.current = setTimeout(refreshRuns, AUTO_REFRESH_DELAY_MS)
      } else {
        toast.warning(response.message || 'El backup no se pudo encolar')
      }
    } catch {
      toast.error('Error al disparar el backup manual')
    } finally {
      setIsRunningBackup(false)
    }
  }, [refreshRuns])

  const columns: Column<BackupRun>[] = useMemo(() => [
    {
      key: 'backup_type',
      label: 'Tipo',
      width: '140px',
      render: (value) => {
        const type = value as BackupType
        const { label, icon: Icon, variant } = TYPE_CONFIG[type]
        return <Badge variant={variant} icon={<Icon className="h-3.5 w-3.5" />}>{label}</Badge>
      },
    },
    {
      key: 'status',
      label: 'Estado',
      width: '140px',
      render: (_value, row) => <StatusBadgeCell run={row} />,
    },
    {
      key: 'started_at',
      label: 'Fecha de inicio',
      width: '220px',
      render: (value) => <span className="text-sm">{formatDateTime(value as string) ?? '—'}</span>,
    },
    {
      key: 'finished_at',
      label: 'Duración',
      width: '110px',
      render: (_value, row) => <span className="text-sm">{formatDuration(row.started_at, row.finished_at)}</span>,
    },
    {
      key: 'size_bytes',
      label: 'Tamaño',
      width: '110px',
      render: (value) => <span className="text-sm">{value != null ? formatBytes(value as number) : '—'}</span>,
    },
    {
      key: 'error_message',
      label: 'Detalle',
      render: (_value, row) => {
        if (row.status !== 'failed' || !row.error_message) {
          return <span className="text-sm text-muted-foreground">—</span>
        }

        const tone = rowTone(row)
        const textClass = tone === 'notConfigured'
          ? 'text-gray-500 dark:text-gray-400'
          : 'text-red-600 dark:text-red-400'
        const isLong = row.error_message.length > ERROR_PREVIEW_LENGTH
        const preview = isLong ? `${row.error_message.slice(0, ERROR_PREVIEW_LENGTH)}…` : row.error_message

        return (
          <div className="max-w-[320px]">
            <span className={`text-xs ${textClass}`} title={row.error_message}>
              {preview}
            </span>
            {isLong && (
              <button
                type="button"
                onClick={() => setErrorDetail(row)}
                className="ml-1.5 text-xs font-medium text-brand-600 hover:underline dark:text-brand-400"
              >
                Ver más
              </button>
            )}
          </div>
        )
      },
    },
  ], [])

  return (
    <div className="space-y-6">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Copias de Seguridad</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Historial de backups automáticos de Postgres y MinIO
          </p>
        </div>

        <div className="flex gap-2 shrink-0">
          <Button variant="secondary" onClick={refreshRuns} leftIcon={<RefreshCw className="w-4 h-4" />}>
            Actualizar
          </Button>
          {canManage && (
            <Button
              variant="primary"
              onClick={handleRunNow}
              isLoading={isRunningBackup}
              loadingText="Encolando..."
              leftIcon={<PlayCircle className="w-4 h-4" />}
            >
              Ejecutar backup ahora
            </Button>
          )}
        </div>
      </div>

      {!isLoading && runs.length === 0 ? (
        <div className="flex justify-center py-12">
          <EmptyState
            icon={<Database className="size-full" />}
            title="Todavía no se corrió ningún backup"
            description="Cuando se ejecute un backup automático o manual, su historial va a aparecer acá."
            primaryAction={canManage ? { label: 'Ejecutar backup ahora', onClick: handleRunNow } : undefined}
          />
        </div>
      ) : (
        <DataTable<BackupRun>
          columns={columns}
          data={runs}
          rowKey="id"
          loading={isLoading && !isFirstLoad}
          emptyMessage="No se encontraron backups"
        />
      )}

      <Modal
        isOpen={errorDetail !== null}
        onClose={() => setErrorDetail(null)}
        title="Detalle del error"
        size="lg"
      >
        {errorDetail && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              {TYPE_CONFIG[errorDetail.backup_type].label} · {formatDateTime(errorDetail.started_at)}
            </p>
            <pre className="whitespace-pre-wrap rounded-lg bg-muted p-3 text-sm text-foreground">
              {errorDetail.error_message}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  )
}
