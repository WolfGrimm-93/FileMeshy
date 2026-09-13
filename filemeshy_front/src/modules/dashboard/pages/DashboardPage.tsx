/**
 * PÁGINA: DASHBOARD
 *
 * Placeholder minimo -- el dashboard original (DashboardPage.tsx) fue
 * borrado en la limpieza de modulos de negocio no relacionado. Diseñar el
 * dashboard real de FileMeshy es trabajo de producto, fuera del alcance de
 * esta limpieza.
 */

import { LayoutDashboard } from 'lucide-react'

export default function DashboardPage() {
  return (
    <div className="flex flex-col h-full">
      <div className="mb-5">
        <h1 className="text-xl font-bold text-foreground">Dashboard</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Panel principal</p>
      </div>

      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="flex justify-center mb-4">
            <div className="bg-brand-500/20 rounded-full p-4">
              <LayoutDashboard className="w-8 h-8 text-brand-500" />
            </div>
          </div>
          <p className="text-muted-foreground">
            El dashboard todavía no tiene contenido para este sistema.
          </p>
        </div>
      </div>
    </div>
  )
}
