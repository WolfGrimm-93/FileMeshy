import { Settings, LogOut, Moon, Sun, User, Users, Loader2, Bell, Calendar, Clock, Check, ExternalLink, ChevronLeft, ChevronRight } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useState, useEffect, useRef, useCallback, useLayoutEffect } from 'react'
import { createPortal } from 'react-dom'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import { useTheme } from '@/app/hooks/useTheme'
import { useSidebarStore } from '@/app/store/sidebarStore'
import { useNotificationStore } from '@/modules/notifications/store/notificationStore'
import SwitchUserModal from '@/modules/auth/components/SwitchUserModal'

interface NavbarProps {
  onLogout?: () => void
  isLoggingOut?: boolean
}

export default function Navbar({
  onLogout,
  isLoggingOut = false,
}: NavbarProps) {
  const { actualTheme, setTheme } = useTheme()
  const isDarkMode = actualTheme === 'dark'
  const { collapsed, toggle } = useSidebarStore()

  const handleToggleTheme = () => {
    setTheme(isDarkMode ? 'light' : 'dark')
  }
  const { user } = useAuth()
  const navigate = useNavigate()
  const [currentTime, setCurrentTime] = useState(new Date())
  const [showNotifDropdown, setShowNotifDropdown] = useState(false)
  const [showSwitchUserModal, setShowSwitchUserModal] = useState(false)
  const notifDropdownRef = useRef<HTMLDivElement>(null)
  const notifButtonRef = useRef<HTMLButtonElement>(null)
  const notifPanelRef = useRef<HTMLDivElement>(null)
  // Posición calculada del panel, portaleado a document.body -- el <header>
  // tiene backdrop-blur-xl, que crea un containing block nuevo para
  // position:fixed (parte de la spec CSS, no un bug del navegador). Un
  // descendiente fixed del header queda posicionado relativo AL HEADER, no al
  // viewport, así que en mobile el panel no llegaba realmente de borde a
  // borde (hallazgo de revisión adversarial, 2026-09-06). Portalear a
  // document.body lo saca del subárbol del header por completo.
  const [notifPanelPos, setNotifPanelPos] = useState<{ top: number; left?: number; right?: number } | null>(null)

  // Store de notificaciones
  const { notifications, unreadCount, fetchNotifications, fetchUnreadCount, markAsRead } = useNotificationStore()

  // Polling de conteo de no leídas cada 30 segundos
  useEffect(() => {
    fetchUnreadCount()
    const interval = setInterval(fetchUnreadCount, 30000)
    return () => clearInterval(interval)
  }, [fetchUnreadCount])

  // Cargar notificaciones recientes al abrir dropdown
  const handleToggleNotifDropdown = useCallback(() => {
    const next = !showNotifDropdown
    setShowNotifDropdown(next)
    if (next) {
      fetchNotifications({ page: 1 })
    }
  }, [showNotifDropdown, fetchNotifications])

  // Cerrar dropdown al hacer click fuera -- el panel está portaleado a
  // document.body (ver notifPanelPos más abajo), así que notifDropdownRef
  // (que solo envuelve el botón) ya no lo contiene; hay que chequear también
  // notifPanelRef antes de cerrar.
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node
      if (
        notifDropdownRef.current && !notifDropdownRef.current.contains(target) &&
        notifPanelRef.current && !notifPanelRef.current.contains(target)
      ) {
        setShowNotifDropdown(false)
      }
    }
    if (showNotifDropdown) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [showNotifDropdown])

  // Calcular la posición del panel portaleado contra el botón real -- se
  // recalcula al abrir y en resize/scroll mientras está abierto, para que
  // siga la campana si la ventana cambia de tamaño.
  useLayoutEffect(() => {
    if (!showNotifDropdown) {
      setNotifPanelPos(null)
      return
    }
    const updatePosition = () => {
      const rect = notifButtonRef.current?.getBoundingClientRect()
      if (!rect) return
      const isMobile = window.innerWidth < 640 // breakpoint `sm` de Tailwind
      if (isMobile) {
        setNotifPanelPos({ top: rect.bottom + 8, left: 16, right: 16 })
      } else {
        setNotifPanelPos({ top: rect.bottom + 8, right: window.innerWidth - rect.right })
      }
    }
    updatePosition()
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition, true)
    return () => {
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition, true)
    }
  }, [showNotifDropdown])

  // Actualizar el reloj cada segundo
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date())
    }, 1000)

    return () => clearInterval(timer)
  }, [])

  // Formatear fecha: "18 Ene 2026"
  const formattedDate = currentTime.toLocaleDateString('es-DO', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })

  // Formatear hora: "02:45:30 PM"
  const formattedTime = currentTime.toLocaleTimeString('es-DO', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })
  
  return (
    <header className="shrink-0 relative z-30 bg-white/90 dark:bg-gray-900/80 backdrop-blur-xl border border-gray-200/70 dark:border-gray-800/60 rounded-2xl shadow-lg shadow-gray-900/5 dark:shadow-black/40">
      <div className="flex items-center justify-between px-4 py-2 gap-4">
        {/* Toggle sidebar - Left side */}
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <button
            onClick={toggle}
            className="shrink-0 flex items-center justify-center w-8 h-8 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-brand-600 dark:hover:text-brand-400 transition-all duration-200"
            title={collapsed ? 'Expandir menú' : 'Colapsar menú'}
          >
            {collapsed ? <ChevronRight className="w-5 h-5" /> : <ChevronLeft className="w-5 h-5" />}
          </button>
        </div>

        {/* User Info & DateTime */}
        <div className="hidden lg:flex items-center gap-3 text-sm">
          {/* Usuario logueado */}
          {user && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
              <User className="w-3.5 h-3.5 text-blue-500 dark:text-blue-400" />
              <span className="text-gray-700 dark:text-gray-300 font-medium capitalize">
                {user.first_name} {user.last_name}
              </span>
            </div>
          )}

          {/* Fecha */}
          <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
            <Calendar className="w-3.5 h-3.5 text-brand-500 dark:text-brand-400" />
            <span className="text-gray-600 dark:text-gray-400">
              {formattedDate}
            </span>
          </div>

          {/* Hora */}
          <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
            <Clock className="w-3.5 h-3.5 text-purple-500 dark:text-purple-400" />
            <span className="text-gray-600 dark:text-gray-400 font-mono">
              {formattedTime}
            </span>
          </div>
        </div>

        {/* Divider */}
        <div className="hidden xl:block w-px h-6 bg-gray-300 dark:bg-gray-700" />

        {/* Actions - Right side */}
        <div className="flex items-center gap-1 sm:gap-2 xl:gap-3">
          {/* Toggle Dark Mode */}
          <button
                onClick={handleToggleTheme}
                className="flex items-center justify-center w-9 h-9 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-brand-600 dark:hover:text-brand-400 rounded-lg transition-all duration-200"
                title={isDarkMode ? 'Modo claro' : 'Modo oscuro'}
                >
                {isDarkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>
         

          {/* Settings Button */}
          <Link
            to="/configuracion"
            className="flex items-center justify-center w-9 h-9 text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-brand-600 dark:hover:text-brand-400 rounded-lg transition-all duration-200"
            title="Configuración"
          >
            <Settings className="w-5 h-5" />
          </Link>

          {/* Notifications Button + Dropdown */}
          <div className="relative" ref={notifDropdownRef}>
            <button
              ref={notifButtonRef}
              onClick={handleToggleNotifDropdown}
              className="relative flex items-center justify-center w-9 h-9 text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-brand-600 dark:hover:text-brand-400 rounded-lg transition-all duration-200"
              title="Notificaciones"
            >
              <Bell className="w-5 h-5" />
              {unreadCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] flex items-center justify-center px-1 text-[10px] font-bold text-white bg-red-500 rounded-full leading-none">
                  {unreadCount > 99 ? '99+' : unreadCount}
                </span>
              )}
            </button>

            {/* Dropdown de notificaciones -- portaleado a document.body (ver
                notifPanelPos): un descendiente `fixed` del <header> con
                backdrop-blur-xl queda posicionado relativo al header, no al
                viewport, así que no puede vivir dentro de ese subárbol. */}
            {showNotifDropdown && notifPanelPos && createPortal(
              <div
                ref={notifPanelRef}
                style={{
                  position: 'fixed',
                  top: notifPanelPos.top,
                  left: notifPanelPos.left,
                  right: notifPanelPos.right,
                  width: notifPanelPos.left !== undefined ? undefined : 384,
                }}
                className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-2xl z-50 overflow-hidden">
                {/* Header */}
                <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                    Notificaciones
                    {unreadCount > 0 && (
                      <span className="ml-2 px-1.5 py-0.5 text-[10px] font-bold bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-400 rounded-full">
                        {unreadCount}
                      </span>
                    )}
                  </h3>
                </div>

                {/* Lista */}
                <div className="max-h-80 overflow-y-auto">
                  {notifications.length === 0 ? (
                    <div className="py-8 text-center">
                      <Bell className="w-8 h-8 text-gray-300 dark:text-gray-600 mx-auto mb-2" />
                      <p className="text-sm text-gray-400 dark:text-gray-500">Sin notificaciones</p>
                    </div>
                  ) : (
                    notifications.slice(0, 5).map((notif) => (
                      <button
                        key={notif.id}
                        onClick={async () => {
                          setShowNotifDropdown(false)
                          if (!notif.is_read) await markAsRead(notif.id)
                          if (notif.action_url) navigate(notif.action_url)
                        }}
                        className={`w-full text-left px-4 py-3 border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors ${
                          !notif.is_read ? 'bg-brand-50/50 dark:bg-brand-900/10' : ''
                        }`}
                      >
                        <div className="flex items-start gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <p className={`text-sm truncate ${!notif.is_read ? 'font-semibold text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-400'}`}>
                                {notif.title}
                              </p>
                              {!notif.is_read && <span className="w-2 h-2 rounded-full bg-brand-500 shrink-0" />}
                            </div>
                            <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                              {notif.message}
                            </p>
                          </div>
                          {!notif.is_read && (
                            <div
                              role="button"
                              tabIndex={0}
                              onClick={(e) => {
                                e.stopPropagation()
                                markAsRead(notif.id)
                              }}
                              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); markAsRead(notif.id) } }}
                              className="shrink-0 p-1 text-gray-400 hover:text-blue-500 rounded-sm transition-colors cursor-pointer"
                              title="Marcar leída"
                            >
                              <Check className="w-3.5 h-3.5" />
                            </div>
                          )}
                        </div>
                      </button>
                    ))
                  )}
                </div>

                {/* Footer */}
                <Link
                  to="/notificaciones"
                  onClick={() => setShowNotifDropdown(false)}
                  className="flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-brand-600 dark:text-brand-400 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors border-t border-gray-200 dark:border-gray-700"
                >
                  Ver todas las notificaciones
                  <ExternalLink className="w-3.5 h-3.5" />
                </Link>
              </div>,
              document.body
            )}
          </div>

          {/* User Profile Button */}
          <Link
            to="/preferencias"
            className="flex items-center justify-center w-9 h-9 text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-brand-600 dark:hover:text-brand-400 rounded-lg transition-all duration-200"
            title="Mis Preferencias"
          >
            <User className="w-5 h-5" />
          </Link>

          {/* Cambiar de usuario (sesión temporal) */}
          <button
            onClick={() => setShowSwitchUserModal(true)}
            className="flex items-center justify-center w-9 h-9 text-gray-900 dark:text-gray-100 hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:text-blue-600 dark:hover:text-blue-400 rounded-lg transition-all duration-200"
            title="Cambiar de usuario"
          >
            <Users className="w-5 h-5" />
          </button>

          {/* Logout Button */}
          <button
            onClick={onLogout}
            disabled={isLoggingOut}
            className="flex items-center justify-center w-9 h-9 text-gray-900 dark:text-gray-100 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 dark:hover:text-red-400 rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            title={isLoggingOut ? 'Cerrando sesión...' : 'Cerrar sesión'}
          >
            {isLoggingOut ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <LogOut className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>

      <SwitchUserModal isOpen={showSwitchUserModal} onClose={() => setShowSwitchUserModal(false)} />
    </header>
  )
}
