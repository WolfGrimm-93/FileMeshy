/**
 * Página de Notificaciones
 * Lista completa de notificaciones del usuario con filtros y acciones
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bell,
  BellOff,
  Check,
  CheckCheck,
  Trash2,
  Filter,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  Info,
  AlertCircle,
  CheckCircle,
  Shield,
  Loader2,
} from 'lucide-react'
import { useNotificationStore } from '../store/notificationStore'
import { toast } from '@/ui/toast/CustomToast'
import { formatDateMedium } from '@/shared/utils/dates'

// Mapeo de tipos a iconos y colores -- solo tipos reales del dominio FileMeshy
// (los de negocio no relacionado -- stock/pagos/ventas/compras/clientes -- se
// podaron junto con sus tasks del backend, ver NotificacionesTab.tsx en Configuración).
const TYPE_CONFIG: Record<string, { icon: typeof Bell; label: string; color: string }> = {
  seguridad: { icon: Shield, label: 'Seguridad', color: 'text-red-600' },
}

const SEVERITY_CONFIG: Record<string, { icon: typeof Info; bgColor: string }> = {
  info: { icon: Info, bgColor: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800' },
  warning: { icon: AlertTriangle, bgColor: 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800' },
  error: { icon: AlertCircle, bgColor: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800' },
  success: { icon: CheckCircle, bgColor: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800' },
}

const FILTER_OPTIONS = [
  { value: '', label: 'Todas' },
  { value: 'seguridad', label: 'Seguridad' },
]

export default function NotificacionesPage() {
  const navigate = useNavigate()
  const {
    notifications,
    unreadCount,
    total,
    page,
    totalPages,
    loading,
    fetchNotifications,
    markAsRead,
    markAllAsRead,
    deleteNotification,
    deleteReadNotifications,
  } = useNotificationStore()

  const [filterType, setFilterType] = useState('')
  const [showUnreadOnly, setShowUnreadOnly] = useState(false)

  useEffect(() => {
    fetchNotifications({ page: 1, type: filterType || undefined, unread_only: showUnreadOnly })
  }, [fetchNotifications, filterType, showUnreadOnly])

  const handlePageChange = (newPage: number) => {
    fetchNotifications({ page: newPage, type: filterType || undefined, unread_only: showUnreadOnly })
  }

  const handleMarkAllRead = async () => {
    await markAllAsRead()
    toast.success('Todas las notificaciones marcadas como leídas')
  }

  const handleDeleteRead = async () => {
    await deleteReadNotifications()
    toast.success('Notificaciones leídas eliminadas')
    fetchNotifications({ page: 1, type: filterType || undefined, unread_only: showUnreadOnly })
  }

  const handleNotificationClick = async (notification: typeof notifications[0]) => {
    if (!notification.is_read) {
      await markAsRead(notification.id)
    }
    if (notification.action_url) {
      navigate(notification.action_url)
    }
  }

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return 'Justo ahora'
    if (diffMins < 60) return `Hace ${diffMins} min`
    if (diffHours < 24) return `Hace ${diffHours}h`
    if (diffDays < 7) return `Hace ${diffDays}d`
    return formatDateMedium(dateStr) ?? ''
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-3">
            <Bell className="w-7 h-7 text-brand-500" />
            Notificaciones
            {unreadCount > 0 && (
              <span className="px-2.5 py-0.5 text-sm font-semibold bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-400 rounded-full">
                {unreadCount} sin leer
              </span>
            )}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {total} notificaciones en total
          </p>
        </div>

        <div className="flex items-center gap-2">
          {unreadCount > 0 && (
            <button
              onClick={handleMarkAllRead}
              className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded-lg transition-colors"
            >
              <CheckCheck className="w-4 h-4" />
              Marcar todas leídas
            </button>
          )}
          <button
            onClick={handleDeleteRead}
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-lg transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            Limpiar leídas
          </button>
        </div>
      </div>

      {/* Filtros */}
      <div className="flex flex-wrap items-center gap-3 p-4 bg-muted rounded-xl border border-border">
        <Filter className="w-4 h-4 text-gray-400" />

        <div className="flex items-center gap-2">
          {FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setFilterType(opt.value)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                filterType === opt.value
                  ? 'bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-400'
                  : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div className="ml-auto">
          <button
            onClick={() => setShowUnreadOnly(!showUnreadOnly)}
            className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              showUnreadOnly
                ? 'bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-400'
                : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
            }`}
          >
            {showUnreadOnly ? <Bell className="w-3.5 h-3.5" /> : <BellOff className="w-3.5 h-3.5" />}
            Solo no leídas
          </button>
        </div>
      </div>

      {/* Lista de notificaciones */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-8 h-8 animate-spin text-brand-500" />
        </div>
      ) : notifications.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <BellOff className="w-16 h-16 text-gray-300 dark:text-gray-600 mb-4" />
          <h3 className="text-lg font-medium text-muted-foreground">
            No hay notificaciones
          </h3>
          <p className="text-sm text-muted-foreground mt-1">
            {filterType || showUnreadOnly
              ? 'No hay resultados con los filtros seleccionados'
              : 'Cuando haya novedades, aparecerán aquí'}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {notifications.map((notif) => {
            const typeConfig = TYPE_CONFIG[notif.type] || { icon: Bell, label: notif.type, color: 'text-gray-500' }
            const severityConfig = SEVERITY_CONFIG[notif.severity] || SEVERITY_CONFIG.info
            const TypeIcon = typeConfig.icon

            return (
              <div
                key={notif.id}
                onClick={() => handleNotificationClick(notif)}
                className={`flex items-start gap-4 p-4 rounded-xl border cursor-pointer transition-all hover:shadow-md ${
                  notif.is_read
                    ? 'bg-muted border-border opacity-75'
                    : `${severityConfig.bgColor} border`
                }`}
              >
                {/* Icono de tipo */}
                <div className={`shrink-0 mt-0.5 ${typeConfig.color}`}>
                  <TypeIcon className="w-5 h-5" />
                </div>

                {/* Contenido */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h4 className={`text-sm font-semibold ${notif.is_read ? 'text-muted-foreground' : 'text-foreground'}`}>
                      {notif.title}
                    </h4>
                    {!notif.is_read && (
                      <span className="w-2 h-2 rounded-full bg-brand-500 shrink-0" />
                    )}
                  </div>
                  <p className={`text-sm mt-0.5 ${notif.is_read ? 'text-muted-foreground' : 'text-gray-600 dark:text-gray-300'}`}>
                    {notif.message}
                  </p>
                  <div className="flex items-center gap-3 mt-2">
                    <span className="text-xs text-muted-foreground">
                      {formatDate(notif.created_at)}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${typeConfig.color} bg-muted`}>
                      {typeConfig.label}
                    </span>
                  </div>
                </div>

                {/* Acciones */}
                <div className="flex items-center gap-1 shrink-0">
                  {!notif.is_read && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        markAsRead(notif.id)
                      }}
                      className="p-1.5 text-gray-400 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                      title="Marcar como leída"
                    >
                      <Check className="w-4 h-4" />
                    </button>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      deleteNotification(notif.id)
                    }}
                    className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                    title="Eliminar"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Paginación */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 bg-muted rounded-xl border border-border">
          <p className="text-sm text-muted-foreground">
            Página {page} de {totalPages} ({total} total)
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handlePageChange(page - 1)}
              disabled={page <= 1}
              className="p-2 rounded-lg text-gray-500 hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => handlePageChange(page + 1)}
              disabled={page >= totalPages}
              className="p-2 rounded-lg text-gray-500 hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
