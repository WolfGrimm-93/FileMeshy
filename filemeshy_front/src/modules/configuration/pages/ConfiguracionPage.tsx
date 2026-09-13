/**
 * PÁGINA: CONFIGURACIÓN DEL SISTEMA
 * Ajustes globales de la empresa y operaciones.
 */

import { useState } from 'react'
import { Bell, ShieldCheck } from 'lucide-react'
import {
  NotificacionesTab,
  SeguridadPage,
} from '../components'

const TAB_GROUPS = [
  {
    label: 'Sistema',
    tabs: [
      { id: 'notificaciones',   nombre: 'Notificaciones',  icono: Bell       },
      { id: 'seguridad',        nombre: 'Seguridad',       icono: ShieldCheck },
    ],
  },
]

const ALL_TABS = TAB_GROUPS.flatMap(g => g.tabs)

export default function ConfiguracionPage() {
  const [activeTab, setActiveTab] = useState<string>(() => {
    const stored = localStorage.getItem('filemeshy_config_active_tab')
    // Si el valor guardado ya no existe (ej. tabs eliminadas como "empresa"/"privacidad"),
    // caer a la primera pestaña disponible en vez de dejar la página en blanco.
    return stored && ALL_TABS.some(t => t.id === stored) ? stored : ALL_TABS[0].id
  })

  const activeTabInfo = ALL_TABS.find(t => t.id === activeTab)

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-foreground">Configuración</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {activeTabInfo?.nombre} — ajustes del sistema
          </p>
        </div>
      </div>

      <div className="flex flex-col md:flex-row gap-5 md:items-start">
        {/* Sidebar */}
        <aside className="w-full md:w-48 shrink-0 md:sticky md:top-6">
          <nav className="bg-card rounded-xl border border-border p-1.5 space-y-3">
            {TAB_GROUPS.map((group, gi) => (
              <div key={group.label}>
                {gi > 0 && <div className="border-t border-border mb-2" />}
                <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {group.label}
                </p>
                <div className="space-y-0.5">
                  {group.tabs.map(tab => {
                    const Icon = tab.icono
                    const active = activeTab === tab.id
                    return (
                      <button
                        key={tab.id}
                        onClick={() => {
                          if (tab.id === activeTab) return
                          setActiveTab(tab.id)
                          localStorage.setItem('filemeshy_config_active_tab', tab.id)
                        }}
                        className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-left transition-all ${
                          active
                            ? 'bg-brand-50 dark:bg-brand-900/20 text-primary'
                            : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                        }`}
                      >
                        <Icon size={15} className={active ? 'text-primary' : 'text-muted-foreground'} />
                        <span className="text-sm font-medium">{tab.nombre}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </nav>
        </aside>

        {/* Contenido */}
        <div className="flex-1 min-w-0 space-y-4">
          {activeTab === 'notificaciones' && <NotificacionesTab />}
          {activeTab === 'seguridad'      && <SeguridadPage />}
        </div>
      </div>
    </div>
  )
}
