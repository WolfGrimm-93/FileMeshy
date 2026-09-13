import { ChevronRight } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { useSidebarStore } from '@/app/store/sidebarStore'

export interface MenuItem {
  id: string
  label: string
  icon: React.ReactNode
  to: string
  tooltip?: string
  badge?: number
  disabled?: boolean
  children?: MenuItem[]
}

interface SidebarNavProps {
  menuItems: MenuItem[]
  onItemClick?: (item: MenuItem) => void
}

export default function SidebarNav({ menuItems, onItemClick }: SidebarNavProps) {
  const location = useLocation()
  const { collapsed } = useSidebarStore()

  const renderMenuItem = (item: MenuItem) => {
    const isActive = location.pathname === item.to || location.pathname.startsWith(item.to + '/')

    const handleClick = () => {
      if (onItemClick && !item.disabled) onItemClick(item)
    }

    const menuContent = (
      <>
        {/* Barra indicadora lateral izquierda */}
        <div
          className={`absolute left-0 top-0 bottom-0 w-1 bg-linear-to-b from-brand-500 to-brand-600 rounded-r-full transition-all duration-300 ${
            isActive
              ? 'opacity-100 scale-y-100'
              : 'opacity-0 scale-y-0 group-hover:opacity-50 group-hover:scale-y-100'
          }`}
        />

        <div className={`flex items-center flex-1 min-w-0 relative z-10 ${collapsed ? 'justify-center' : 'gap-2'}`}>
          {/* Icono */}
          <span
            className={`shrink-0 transition-all duration-300 ${
              isActive
                ? 'text-white scale-110'
                : item.disabled
                ? 'text-gray-400 dark:text-gray-600'
                : 'text-gray-600 dark:text-gray-400 group-hover:text-brand-600 dark:group-hover:text-brand-400 group-hover:scale-110'
            }`}
          >
            {item.icon}
          </span>

          {/* Label — se oculta cuando está colapsado */}
          <span
            className={`
              font-medium truncate transition-all duration-300 text-sm
              ${item.disabled ? 'opacity-50' : ''}
              ${isActive ? 'text-white font-semibold' : item.disabled ? 'text-gray-400 dark:text-gray-600' : 'text-gray-700 dark:text-gray-300 group-hover:text-brand-600 dark:group-hover:text-brand-400'}
              ${collapsed ? 'w-0 opacity-0 overflow-hidden' : 'flex-1 opacity-100'}
            `}
          >
            {item.label}
          </span>

          {/* Badge */}
          {item.badge && item.badge > 0 && (
            <span className={`shrink-0 min-w-[18px] h-[18px] px-1 bg-linear-to-r from-red-500 to-red-600 text-white text-[10px] font-bold rounded-full flex items-center justify-center shadow-md ${collapsed ? 'absolute -top-1 -right-1' : ''}`}>
              {item.badge > 99 ? '99+' : item.badge}
            </span>
          )}

          {/* Chevron activo — solo expandido */}
          {isActive && !collapsed && (
            <ChevronRight className="shrink-0 w-4 h-4 text-white" />
          )}
        </div>

        {/* Hover glow */}
        {!isActive && !item.disabled && (
          <div className="absolute inset-0 bg-linear-to-r from-brand-500/5 to-brand-600/5 dark:from-brand-400/10 dark:to-brand-500/10 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
        )}

        {/* Tooltip — solo cuando está colapsado */}
        {collapsed && (
          <div className="
            absolute left-full ml-2.5 z-100
            pointer-events-none
            opacity-0 group-hover:opacity-100
            translate-x-2 group-hover:translate-x-0
            transition-all duration-200 ease-out
          ">
            <div className="
              flex items-center gap-0
              bg-gray-900 dark:bg-gray-800
              rounded-lg shadow-xl
              overflow-hidden
              whitespace-nowrap
            ">
              {/* Acento naranja */}
              <div className="w-1 self-stretch bg-linear-to-b from-brand-400 to-brand-600 shrink-0" />
              <span className="px-3 py-2 text-xs font-semibold text-white tracking-wide">
                {item.tooltip || item.label}
              </span>
            </div>
            {/* Flecha */}
            <div className="absolute right-full top-1/2 -translate-y-1/2 border-[5px] border-transparent border-r-gray-900 dark:border-r-gray-800" />
          </div>
        )}
      </>
    )

    const linkClasses = `
      relative flex items-center rounded-lg transition-all duration-300 group overflow-visible
      ${collapsed ? 'px-0 py-2 justify-center' : 'px-2.5 py-2'}
      ${
        isActive
          ? 'bg-linear-to-r from-brand-500 to-brand-600 text-white shadow-lg shadow-brand-200/50 dark:shadow-brand-900/50 scale-[1.02]'
          : item.disabled
          ? 'text-gray-400 dark:text-gray-600 cursor-not-allowed opacity-60'
          : 'text-gray-700 dark:text-gray-300 hover:bg-brand-50 dark:hover:bg-brand-900/10 hover:scale-[1.02]'
      }
    `.trim()

    if (item.disabled) {
      return (
        <div key={item.id} className={linkClasses}>
          {menuContent}
        </div>
      )
    }

    return (
      <Link
        key={item.id}
        to={item.to}
        onClick={handleClick}
        className={linkClasses}
        aria-label={item.label}
        aria-current={isActive ? 'page' : undefined}
        title={collapsed ? (item.tooltip || item.label) : undefined}
      >
        {menuContent}
      </Link>
    )
  }

  return (
    <nav className="space-y-1.5" role="navigation" aria-label="Navegación principal">
      {menuItems.map(renderMenuItem)}
    </nav>
  )
}
