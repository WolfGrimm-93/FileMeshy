/**
 * Servicio de notificaciones
 * Gestiona las notificaciones del usuario autenticado
 */
import axiosInstance from '@/shared/config/axios'

export interface Notification {
  id: string
  user_id: string
  title: string
  message: string
  type: string
  severity: 'info' | 'warning' | 'error' | 'success'
  is_read: boolean
  read_at: string | null
  action_url: string | null
  extra_data: Record<string, unknown> | null
  created_at: string
}

export interface NotificationListResponse {
  items: Notification[]
  total: number
  unread_count: number
  page: number
  page_size: number
  total_pages: number
}

export interface UnreadCountResponse {
  unread_count: number
}

interface GetNotificationsParams {
  page?: number
  page_size?: number
  unread_only?: boolean
  type?: string
}

class NotificationService {
  /**
   * Obtener notificaciones con paginación
   */
  async getNotifications(params: GetNotificationsParams = {}): Promise<NotificationListResponse> {
    const response = await axiosInstance.get('/notifications', { params })
    return response.data
  }

  /**
   * Obtener conteo de no leídas
   */
  async getUnreadCount(): Promise<number> {
    const response = await axiosInstance.get('/notifications/unread-count')
    return response.data.unread_count
  }

  /**
   * Obtener una notificación por ID
   */
  async getNotification(id: string): Promise<Notification> {
    const response = await axiosInstance.get(`/notifications/${id}`)
    return response.data
  }

  /**
   * Marcar una notificación como leída
   */
  async markAsRead(id: string): Promise<Notification> {
    const response = await axiosInstance.put(`/notifications/${id}/read`)
    return response.data
  }

  /**
   * Marcar todas como leídas
   */
  async markAllAsRead(): Promise<{ message: string; count: number }> {
    const response = await axiosInstance.put('/notifications/read-all')
    return response.data
  }

  /**
   * Eliminar una notificación
   */
  async deleteNotification(id: string): Promise<void> {
    await axiosInstance.delete(`/notifications/${id}`)
  }

  /**
   * Eliminar todas las leídas
   */
  async deleteReadNotifications(): Promise<{ message: string; count: number }> {
    const response = await axiosInstance.delete('/notifications')
    return response.data
  }
}

export const notificationService = new NotificationService()
