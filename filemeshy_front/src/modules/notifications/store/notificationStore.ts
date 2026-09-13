/**
 * Store de notificaciones con Zustand
 * Gestiona el estado de notificaciones en el frontend
 */
import { create } from 'zustand'
import { notificationService } from '../services/notification.service'
import type { Notification } from '../services/notification.service'

interface NotificationState {
  // Estado
  notifications: Notification[]
  unreadCount: number
  total: number
  page: number
  totalPages: number
  loading: boolean

  // Acciones
  fetchNotifications: (params?: { page?: number; unread_only?: boolean; type?: string }) => Promise<void>
  fetchUnreadCount: () => Promise<void>
  markAsRead: (id: string) => Promise<void>
  markAllAsRead: () => Promise<void>
  deleteNotification: (id: string) => Promise<void>
  deleteReadNotifications: () => Promise<void>
  reset: () => void
}

export const useNotificationStore = create<NotificationState>((set, get) => ({
  notifications: [],
  unreadCount: 0,
  total: 0,
  page: 1,
  totalPages: 1,
  loading: false,

  fetchNotifications: async (params) => {
    set({ loading: true })
    try {
      const data = await notificationService.getNotifications({
        page: params?.page ?? 1,
        page_size: 20,
        unread_only: params?.unread_only,
        type: params?.type,
      })
      set({
        notifications: data.items,
        unreadCount: data.unread_count,
        total: data.total,
        page: data.page,
        totalPages: data.total_pages,
      })
    } catch (error) {
      console.error('Error cargando notificaciones:', error)
    } finally {
      set({ loading: false })
    }
  },

  fetchUnreadCount: async () => {
    try {
      const count = await notificationService.getUnreadCount()
      set({ unreadCount: count })
    } catch (error) {
      console.error('Error obteniendo conteo de no leídas:', error)
    }
  },

  markAsRead: async (id: string) => {
    try {
      await notificationService.markAsRead(id)
      set((state) => ({
        notifications: state.notifications.map((n) =>
          n.id === id ? { ...n, is_read: true, read_at: new Date().toISOString() } : n
        ),
        unreadCount: Math.max(0, state.unreadCount - 1),
      }))
    } catch (error) {
      console.error('Error marcando como leída:', error)
    }
  },

  markAllAsRead: async () => {
    try {
      await notificationService.markAllAsRead()
      set((state) => ({
        notifications: state.notifications.map((n) => ({
          ...n,
          is_read: true,
          read_at: n.read_at ?? new Date().toISOString(),
        })),
        unreadCount: 0,
      }))
    } catch (error) {
      console.error('Error marcando todas como leídas:', error)
    }
  },

  deleteNotification: async (id: string) => {
    try {
      await notificationService.deleteNotification(id)
      const state = get()
      const removed = state.notifications.find((n) => n.id === id)
      set({
        notifications: state.notifications.filter((n) => n.id !== id),
        total: state.total - 1,
        unreadCount: removed && !removed.is_read ? state.unreadCount - 1 : state.unreadCount,
      })
    } catch (error) {
      console.error('Error eliminando notificación:', error)
    }
  },

  deleteReadNotifications: async () => {
    try {
      await notificationService.deleteReadNotifications()
      set((state) => {
        const unread = state.notifications.filter((n) => !n.is_read)
        return {
          notifications: unread,
          total: unread.length,
        }
      })
    } catch (error) {
      console.error('Error eliminando leídas:', error)
    }
  },

  reset: () => {
    set({
      notifications: [],
      unreadCount: 0,
      total: 0,
      page: 1,
      totalPages: 1,
      loading: false,
    })
  },
}))
