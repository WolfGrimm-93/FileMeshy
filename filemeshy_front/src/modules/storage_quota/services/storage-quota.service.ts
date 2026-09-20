import axiosInstance from '@/shared/config/axios'

// ===== INTERFACES =====
// Contrato fijado en conjunto con el backend (ver otro agente trabajando en
// paralelo sobre el endpoint) -- no cambiar de este lado sin coordinar.

export interface StorageQuotaItem {
  user_id: string
  email: string
  first_name: string
  last_name: string
  limit_bytes: number | null // null = sin límite
  bytes_used: number
}

export interface StorageQuotaFilters {
  skip?: number
  limit?: number
  search?: string
}

export interface StorageQuotasResponse {
  items: StorageQuotaItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface StorageQuotaUpdate {
  limit_bytes: number | null
}

export interface StorageCapacity {
  total_bytes: number | null
  used_bytes: number | null
  free_bytes: number | null
}

export interface MyStorageQuota {
  limit_bytes: number | null // null = sin límite
  bytes_used: number
}

// ===== SERVICE =====
class StorageQuotaService {
  private basePath = '/storage-quotas'

  /**
   * Obtener lista de cuotas por usuario, con paginación y búsqueda
   */
  async getQuotas(params?: StorageQuotaFilters): Promise<StorageQuotasResponse> {
    const response = await axiosInstance.get<StorageQuotasResponse>(this.basePath, { params })
    return response.data
  }

  /**
   * Actualizar (upsert) el límite de cuota de un usuario
   */
  async updateQuota(userId: string, data: StorageQuotaUpdate): Promise<StorageQuotaItem> {
    const response = await axiosInstance.put<StorageQuotaItem>(`${this.basePath}/${userId}`, data)
    return response.data
  }

  /**
   * Obtener la capacidad real de disco (total/usado/libre). Puede venir todo
   * en null si el backend no pudo leer la capacidad real -- la UI lo muestra
   * como "No disponible" en ese caso.
   */
  async getCapacity(): Promise<StorageCapacity> {
    const response = await axiosInstance.get<StorageCapacity>(`${this.basePath}/capacity`)
    return response.data
  }

  /**
   * Obtener la cuota propia del usuario logueado (para el indicador del sidebar).
   */
  async getMyQuota(): Promise<MyStorageQuota> {
    const response = await axiosInstance.get<MyStorageQuota>(`${this.basePath}/me`)
    return response.data
  }
}

export const storageQuotaService = new StorageQuotaService()
