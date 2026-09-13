/**
 * SERVICIO: Logs de Auditoría
 * Conecta con el endpoint /audit-logs/ del backend (requiere autenticación)
 */

import axiosInstance from '@/shared/config/axios'

// ===========================
// Tipos
// ===========================

export interface AuditLog {
  id: string
  user_id: string
  user_email: string
  action: string           // CREATE | UPDATE | DELETE
  table_name: string
  record_id: string
  ip_address: string
  endpoint: string
  method: string
  created_at: string
}

export interface AuditLogDetail extends AuditLog {
  old_data?: Record<string, unknown>
  new_data?: Record<string, unknown>
  changes?: Record<string, unknown>
}

export interface AuditLogListResponse {
  logs: AuditLog[]
  total: number
  skip: number
  limit: number
  cached?: boolean
}

export interface AuditStats {
  total_logs: number
  by_action: Record<string, number>
  top_tables: Array<{ table: string; count: number }>
}

export interface AuditLogFilters {
  user_id?: string
  user_email?: string
  action?: string
  table_name?: string
  start_date?: string
  end_date?: string
  search?: string
  skip?: number
  limit?: number
}

// ===========================
// Service
// ===========================

class AuditLogService {
  private baseURL = '/audit-logs'

  async getLogs(filters?: AuditLogFilters): Promise<AuditLogListResponse> {
    const response = await axiosInstance.get<AuditLogListResponse>(
      `${this.baseURL}/`,
      { params: filters }
    )
    return response.data
  }

  async getLogDetail(logId: string): Promise<AuditLogDetail> {
    const response = await axiosInstance.get(`${this.baseURL}/${logId}`)
    return response.data.data
  }

  async getStats(): Promise<AuditStats> {
    const response = await axiosInstance.get<AuditStats>(`${this.baseURL}/stats/summary`)
    return response.data
  }
}

export const auditLogService = new AuditLogService()
