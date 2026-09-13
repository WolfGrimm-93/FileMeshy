import {
  LayoutDashboard,
  Users,
  ScrollText,
  Folder,
  HardDrive,
} from 'lucide-react'
import { useAuthStore } from '@/modules/auth/store/authStore'
import { useSidebarStore } from '@/app/store/sidebarStore'
import { useConfig } from '@/modules/configuration/hooks/useConfig'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import SidebarHeader from './SidebarHeader'
import SidebarNav, { type MenuItem } from './SidebarNav'

export default function Sidebar() {
  const { user } = useAuthStore()
  const { hasPermission } = useAuth()
  const { collapsed } = useSidebarStore()
  const { config } = useConfig()

  const isAdmin = user?.role === 'ADMIN' || user?.role === 'SUPER_ADMIN'

  const allItems: (MenuItem & { permission?: string | string[] })[] = [
    {
      id: 'dashboard',
      label: 'Dashboard',
      icon: <LayoutDashboard className="w-5 h-5" />,
      to: '/dashboard',
      tooltip: 'Dashboard',
      permission: 'dashboard.view',
    },
    ...(isAdmin ? [{
      id: 'logs',
      label: 'Logs de Auditoría',
      icon: <ScrollText className="w-5 h-5" />,
      to: '/logs',
      tooltip: 'Logs de Auditoría',
    }] : []),
    {
      id: 'archivos',
      label: 'Archivos',
      icon: <Folder className="w-5 h-5" />,
      to: '/archivos',
      tooltip: 'Archivos',
      permission: 'files.view',
    },
    {
      id: 'usuarios',
      label: 'Usuarios',
      icon: <Users className="w-5 h-5" />,
      to: '/usuarios',
      tooltip: 'Usuarios',
      permission: 'users.view',
    },
    {
      id: 'cuotas-almacenamiento',
      label: 'Cuotas de Almacenamiento',
      icon: <HardDrive className="w-5 h-5" />,
      to: '/cuotas-almacenamiento',
      tooltip: 'Cuotas de Almacenamiento',
      permission: 'storage_quotas.view',
    },
  ]

  const menuItems = allItems.filter(({ permission }) => {
    if (!permission) return true
    return Array.isArray(permission)
      ? permission.some(hasPermission)
      : hasPermission(permission)
  })

  return (
    <aside
      className={`
        h-full flex flex-col
        bg-white/90 dark:bg-gray-900/80 backdrop-blur-xl
        border border-gray-200/70 dark:border-gray-800/60
        rounded-2xl shadow-lg shadow-gray-900/5 dark:shadow-black/40
        overflow-x-visible overflow-y-hidden
        transition-all duration-300 ease-in-out
        ${collapsed ? 'w-14' : 'w-52'}
      `}
    >
      <div className="flex flex-col h-full overflow-hidden">
        {/* Header */}
        <div className="shrink-0 p-3">
          <SidebarHeader business={{
            nombre: config?.company?.business_name ?? 'FileMeshy',
            tipo: 'Almacenamiento de Archivos',
            imagen: config?.company?.logo_icon_path ?? config?.company?.logo_path ?? undefined,
          }} />
        </div>

        {/* Navigation - Scrollable. overflow-x-visible para los tooltips en modo colapsado */}
        <div className="flex-1 overflow-y-auto overflow-x-visible scrollbar-hide px-2 py-2">
          <SidebarNav menuItems={menuItems} />
        </div>
      </div>
    </aside>
  )
}
