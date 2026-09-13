/**
 * Página /modulo-no-disponible - El módulo fue desactivado por un administrador
 *
 * Se muestra cuando ModuleGuard (app/routes/loaders.ts) detecta que el flag
 * del módulo está apagado en Configuración → Módulos. Distinta de /forbidden
 * (permisos insuficientes) y /unauthorized: acá el usuario SÍ tendría acceso,
 * pero el módulo está apagado para todo el sistema.
 */

import { useNavigate } from 'react-router-dom'
import { PowerOff, ArrowLeft } from 'lucide-react'

export function ModuloNoDisponiblePage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-white dark:bg-slate-950 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="bg-gray-50 dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-800 p-8 text-center">
          <div className="flex justify-center mb-6">
            <div className="bg-brand-500/20 rounded-full p-4">
              <PowerOff className="w-8 h-8 text-brand-500" />
            </div>
          </div>

          <h1 className="text-3xl font-bold text-foreground mb-2">
            Módulo No Disponible
          </h1>

          <p className="text-muted-foreground mb-6">
            Este módulo no está disponible en este momento.
          </p>

          <div className="flex gap-3">
            <button
              onClick={() => navigate(-1)}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg border border-gray-300 dark:border-slate-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-slate-800 transition"
            >
              <ArrowLeft className="w-4 h-4" />
              Volver
            </button>

            <button
              onClick={() => navigate('/dashboard')}
              className="flex-1 px-4 py-2 rounded-lg bg-brand-500 text-white font-medium hover:bg-brand-600 transition"
            >
              Dashboard
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ModuloNoDisponiblePage
