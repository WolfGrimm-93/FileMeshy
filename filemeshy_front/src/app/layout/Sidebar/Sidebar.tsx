import { useEffect, useState } from 'react'
import {
  LayoutDashboard,
  Users,
  ScrollText,
  Folder,
  HardDrive,
  Share2,
} from 'lucide-react'
import { useAuthStore } from '@/modules/auth/store/authStore'
import { useSidebarStore } from '@/app/store/sidebarStore'
import { useConfig } from '@/modules/configuration/hooks/useConfig'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import { Permission } from '@/app/routes'
import { Progress } from '@/ui/progress/Progress'
import { formatBytes } from '@/shared/utils/downloadFile'
import { storageQuotaService, type MyStorageQuota } from '@/modules/storage_quota/services/storage-quota.service'
import SidebarHeader from './SidebarHeader'
import SidebarNav, { type MenuItem } from './SidebarNav'

/**
 * Indicador de cuota de almacenamiento propia. Vive en el Sidebar (sección visible,
 * antes de donde iría SidebarFooter) para que el usuario vea de un vistazo cuánto
 * lleva usado, sin tener que entrar a Configuración/Cuotas.
 *
 * Si `limit_bytes` es null (sin límite asignado) no se muestra barra de progreso,
 * solo el total usado en texto -- no tiene sentido una barra sin techo.
 *
 * Falla en silencio (sin toast): es un indicador secundario, no bloquea el uso del
 * sidebar si el endpoint todavía no existe o falla puntualmente.
 */
function SidebarStorageQuota({ collapsed }: { collapsed: boolean }) {
  const [quota, setQuota] = useState<MyStorageQuota | null>(null)

  useEffect(() => {
    let cancelled = false
    storageQuotaService
      .getMyQuota()
      .then((data) => {
        if (!cancelled) setQuota(data)
      })
      .catch(() => {
        // Indicador secundario -- si falla (ej. endpoint aún no desplegado), simplemente no se muestra.
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (!quota || collapsed) return null

  const { limit_bytes: limitBytes, bytes_used: bytesUsed } = quota

  return (
    <div className="shrink-0 px-3 pb-2">
      <div className="rounded-lg bg-gray-100 dark:bg-gray-800/60 px-3 py-2.5">
        <div className="flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-gray-400">
          <HardDrive className="size-3.5" />
          Almacenamiento
        </div>
        {limitBytes === null ? (
          <p className="mt-1.5 text-sm font-semibold text-gray-700 dark:text-gray-300">
            {formatBytes(bytesUsed)} usados
          </p>
        ) : (
          <>
            <Progress
              value={bytesUsed}
              max={limitBytes}
              size="sm"
              className="mt-2"
              variant={bytesUsed / limitBytes >= 0.9 ? 'danger' : bytesUsed / limitBytes >= 0.7 ? 'warning' : 'default'}
            />
            <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
              {formatBytes(bytesUsed)} de {formatBytes(limitBytes)}
            </p>
          </>
        )}
      </div>
    </div>
  )
}

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
      id: 'compartido-conmigo',
      label: 'Compartido conmigo',
      icon: <Share2 className="w-5 h-5" />,
      to: '/compartido-conmigo',
      tooltip: 'Compartido conmigo',
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

        {/* Cuota de almacenamiento propia -- sección visible, antes de SidebarFooter */}
        {hasPermission(Permission.VIEW_FILES) && <SidebarStorageQuota collapsed={collapsed} />}
      </div>
    </aside>
  )
}
