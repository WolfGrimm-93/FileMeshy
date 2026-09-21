import axiosInstance from '@/shared/config/axios'

// ===== INTERFACES =====
// Contrato fijado en conjunto con el backend (ver otro agente trabajando en
// paralelo sobre el endpoint /admin/backups) -- no cambiar de este lado sin
// coordinar en la revisión adversarial.

export type BackupType = 'postgres' | 'minio'
export type BackupStatus = 'success' | 'failed' | 'running'

export interface BackupRun {
  id: string
  backup_type: BackupType
  status: BackupStatus
  started_at: string
  finished_at: string | null
  size_bytes: number | null
  storage_location: string | null
  error_message: string | null
}

// Forma real de la respuesta de GET /admin/backups -- viene envuelta en
// paginación aunque hoy el frontend no pagina (confirmado en revisión
// adversarial contra el backend real: NO es un array plano).
interface BackupsListResponse {
  items: BackupRun[]
  total: number
}

export interface RunBackupResponse {
  queued: boolean
  message: string
}

// ===== SERVICE =====
class BackupsService {
  private basePath = '/admin/backups'

  /**
   * Obtener el historial de backups (Postgres + MinIO), más recientes primero
   * (orden esperado del backend). El backend envuelve la lista en
   * `{items, total}` -- acá se desenvuelve para que el resto del frontend
   * siga trabajando con un array simple (sin paginación por ahora).
   */
  async list(): Promise<BackupRun[]> {
    const response = await axiosInstance.get<BackupsListResponse>(this.basePath)
    return response.data.items
  }

  /**
   * Disparar un backup manual. Sin body -- el backend decide qué correr.
   * La respuesta solo confirma que quedó encolado (`queued`), no que ya
   * terminó -- viene acompañada de un `message` para mostrar tal cual.
   */
  async runNow(): Promise<RunBackupResponse> {
    const response = await axiosInstance.post<RunBackupResponse>(`${this.basePath}/run`)
    return response.data
  }
}

export const backupsService = new BackupsService()
