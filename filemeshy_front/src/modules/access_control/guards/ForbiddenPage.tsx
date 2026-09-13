/**
 * Página /forbidden - Acceso denegado por permisos insuficientes
 * 
 * Se muestra cuando el usuario intenta acceder a un recurso para el que
 * NO tiene permisos (403 Forbidden)
 * 
 * Diferente de /login (401 Unauthorized - sesión inválida)
 */

import { useNavigate } from 'react-router-dom'
import { AlertCircle, ArrowLeft } from 'lucide-react'

export function ForbiddenPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-white dark:bg-slate-950 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Contenedor principal */}
        <div className="bg-gray-50 dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-800 p-8 text-center">
          {/* Icono de error */}
          <div className="flex justify-center mb-6">
            <div className="bg-red-500/20 rounded-full p-4">
              <AlertCircle className="w-8 h-8 text-red-500" />
            </div>
          </div>

          {/* Título */}
          <h1 className="text-3xl font-bold text-foreground mb-2">
            Acceso Denegado
          </h1>

          {/* Código de error */}
          <div className="text-5xl font-bold text-red-500/50 mb-4">
            403
          </div>

          {/* Descripción */}
          <p className="text-muted-foreground mb-6">
            No tienes permisos para acceder a este recurso.
            Si crees que es un error, contacta con tu administrador.
          </p>

          {/* Detalles técnicos en desarrollo */}
          {import.meta.env.DEV && (
            <div className="bg-gray-100 dark:bg-slate-800 rounded-sm p-4 mb-6 text-left">
              <p className="text-xs text-gray-500 font-mono">
                Código HTTP: 403 Forbidden
              </p>
              <p className="text-xs text-gray-500 font-mono">
                Causa: Permisos insuficientes
              </p>
            </div>
          )}

          {/* Botones */}
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

          {/* Contacto */}
          <div className="mt-6 pt-6 border-t border-gray-200 dark:border-slate-800">
            <p className="text-sm text-gray-500">
              ¿Necesitas ayuda?{' '}
              <a
                href="mailto:wolfgrimm.wd@gmail.com"
                className="text-brand-500 hover:text-brand-400 transition"
              >
                Contacta con soporte
              </a>
            </p>
          </div>
        </div>

        {/* Footer informativo */}
        <div className="mt-8 text-center text-xs text-muted-foreground/50">
          <p>
            Esto sucede cuando intentas acceder a una funcionalidad que
            no está autorizada para tu rol
          </p>
        </div>
      </div>
    </div>
  )
}

export default ForbiddenPage
