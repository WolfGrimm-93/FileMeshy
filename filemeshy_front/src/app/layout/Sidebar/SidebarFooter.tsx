import { Settings, LogOut, Moon, Sun, ChevronUp, User } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTheme } from '@/app/hooks/useTheme'

interface SidebarFooterProps {
  userName?: string
  userEmail?: string
  userAvatar?: string
  onLogout?: () => void
}

export default function SidebarFooter({
  userName = 'Administrador',
  userEmail = 'admin@filemeshy.dev',
  userAvatar,
  onLogout,
}: SidebarFooterProps) {
  const { actualTheme, setTheme } = useTheme()
  const isDarkMode = actualTheme === 'dark'

  const handleToggleTheme = () => {
    setTheme(isDarkMode ? 'light' : 'dark')
  }
  const [showUserMenu, setShowUserMenu] = useState(false)

  return (
    <div className="mt-auto pt-4 space-y-3 border-t border-gray-200 dark:border-gray-800">
      {/* Botones de acción rápida */}
      <div className="flex items-center gap-2 px-3">
        <button
          onClick={handleToggleTheme}
          className="flex-1 flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-all duration-200"
          title={isDarkMode ? 'Modo claro' : 'Modo oscuro'}
        >
          {isDarkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>
        
        <Link
          to="/configuracion"
          className="flex-1 flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-all duration-200"
          title="Configuración"
        >
          <Settings className="w-4 h-4" />
        </Link>
      </div>

      {/* User info con dropdown */}
      <div className="relative">
        <button
          onClick={() => setShowUserMenu(!showUserMenu)}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-all duration-200 group"
        >
          {/* Avatar */}
          <div className="shrink-0 w-9 h-9 rounded-lg bg-linear-to-br from-brand-400 to-brand-600 flex items-center justify-center text-white font-semibold shadow-md">
            {userAvatar ? (
              <img
                src={userAvatar}
                alt={userName}
                className="w-full h-full rounded-lg object-cover"
              />
            ) : (
              <User className="w-5 h-5" />
            )}
          </div>

          {/* User info */}
          <div className="flex-1 text-left min-w-0">
            <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
              {userName}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
              {userEmail}
            </p>
          </div>

          {/* Arrow */}
          <ChevronUp
            className={`shrink-0 w-4 h-4 text-gray-400 transition-transform duration-200 ${
              showUserMenu ? 'rotate-180' : ''
            }`}
          />
        </button>

        {/* Dropdown menu */}
        {showUserMenu && (
          <div className="absolute bottom-full left-0 right-0 mb-2 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-xl">
            <Link
              to="/perfil"
              className="flex items-center gap-3 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              onClick={() => setShowUserMenu(false)}
            >
              <User className="w-4 h-4" />
              Ver perfil
            </Link>
            
            <Link
              to="/configuracion"
              className="flex items-center gap-3 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              onClick={() => setShowUserMenu(false)}
            >
              <Settings className="w-4 h-4" />
              Configuración
            </Link>

            <div className="my-1 h-px bg-gray-200 dark:bg-gray-700" />

            <button
              onClick={() => {
                setShowUserMenu(false)
                onLogout?.()
              }}
              className="w-full flex items-center gap-3 px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
            >
              <LogOut className="w-4 h-4" />
              Cerrar sesión
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
