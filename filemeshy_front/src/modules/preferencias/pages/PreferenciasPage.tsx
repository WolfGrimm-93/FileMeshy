/**
 * PÁGINA: PREFERENCIAS DE USUARIO
 * Configuraciones personales: perfil, seguridad, apariencia, notificaciones
 * Accesible para todos los usuarios autenticados
 * 
 * NUEVA ARQUITECTURA:
 * - Componentes modulares
 * - Conexión directa con endpoints del backend
 * - Interfaz simplificada sin panel derecho
 */

import { useState } from 'react'
import { User, Shield, Bell } from 'lucide-react'
import {
  MiPerfilComponent,
  SeguridadComponent,
  NotificacionesComponent
} from '@/modules/preferencias'

export default function PreferenciasPage() {
  const [activeTab, setActiveTab] = useState('perfil')

  const tabs = [
    { id: 'perfil', nombre: 'Mi Perfil', icono: User },
    { id: 'seguridad', nombre: 'Seguridad', icono: Shield },
    { id: 'notificaciones', nombre: 'Notificaciones', icono: Bell },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-foreground mb-2">
          Mis Preferencias
        </h2>
        <p className="text-muted-foreground">
          Personaliza tu experiencia en FileMeshy
        </p>
      </div>

      <div className="flex flex-col lg:flex-row gap-6 lg:items-start">
        {/* Sidebar de tabs - Se mantiene igual */}
        <div className="lg:w-64 lg:sticky lg:top-6 bg-card rounded-2xl border border-border p-4 shrink-0">
          <nav className="space-y-2">
            {tabs.map(tab => {
              const IconComponent = tab.icono
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center space-x-3 px-3 py-2 rounded-lg text-left transition-colors ${
                    activeTab === tab.id
                      ? 'bg-brand-100 dark:bg-brand-900/30 text-primary font-medium'
                      : 'text-foreground/80 hover:bg-muted'
                  }`}
                >
                  <IconComponent size={18} />
                  <span>{tab.nombre}</span>
                </button>
              )
            })}
          </nav>
        </div>

        {/* Contenido principal - Rediseñado con componentes modulares */}
        <div className="flex-1 bg-card rounded-2xl border border-border overflow-hidden">
          <div className="p-6">
            {activeTab === 'perfil' && <MiPerfilComponent />}
            {activeTab === 'seguridad' && <SeguridadComponent />}
{activeTab === 'notificaciones' && <NotificacionesComponent />}
          </div>
        </div>
      </div>
    </div>
  )
}
