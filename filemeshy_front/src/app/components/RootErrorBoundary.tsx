/**
 * Root Error Boundary para React Router
 * Se usa como errorElement en las rutas
 */

import { useRouteError, useNavigate, isRouteErrorResponse } from 'react-router-dom'
import { AlertCircle, ArrowLeft, RefreshCw, Home } from 'lucide-react'
import { Button } from '@/ui/buttons/Button'

interface ErrorData {
  message?: string
  details?: string
}

export function RootErrorBoundary() {
  const error = useRouteError()
  const navigate = useNavigate()

  let errorMessage = 'Ha ocurrido un error inesperado'
  let errorDetails = ''
  let statusCode = 500

  if (isRouteErrorResponse(error)) {
    statusCode = error.status
    const data = error.data as ErrorData | undefined
    errorMessage = error.statusText || data?.message || 'Error de ruta'
    errorDetails = data?.details || ''
  } else if (error instanceof Error) {
    errorMessage = error.message
    errorDetails = error.stack || ''
  }

  return (
    <div className="min-h-screen w-full overflow-hidden relative bg-linear-to-br from-gray-50 via-brand-50/30 to-gray-50 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
      {/* Fondo decorativo */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div
          className="absolute inset-0 opacity-[0.03] dark:opacity-[0.05]"
          style={{
            backgroundImage: `
              linear-gradient(to right, currentColor 1px, transparent 1px),
              linear-gradient(to bottom, currentColor 1px, transparent 1px)
            `,
            backgroundSize: '60px 60px',
          }}
        />
        <div className="absolute -top-24 -left-24 w-96 h-96 bg-brand-500/10 dark:bg-brand-500/5 rounded-full blur-3xl" />
        <div className="absolute -bottom-24 -right-24 w-96 h-96 bg-brand-500/10 dark:bg-brand-500/5 rounded-full blur-3xl" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-linear-to-br from-brand-500/5 to-transparent dark:from-brand-500/3 rounded-full blur-3xl" />
      </div>

      {/* Contenido */}
      <div className="relative flex min-h-screen items-center justify-center p-4 sm:p-6 md:p-8">
        <div className="w-full max-w-sm">
          <div className="bg-white/70 dark:bg-gray-800/60 backdrop-blur-xs border border-gray-200 dark:border-gray-700 rounded-2xl p-8 text-center shadow-xs">

            {/* Icono */}
            <div className="flex justify-center mb-6">
              <div className="w-20 h-20 rounded-2xl bg-red-500/10 flex items-center justify-center">
                <AlertCircle className="w-10 h-10 text-red-500 dark:text-red-400" strokeWidth={1.5} />
              </div>
            </div>

            {/* Código y título */}
            <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 tracking-widest uppercase mb-2">
              Error {statusCode}
            </p>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
              Algo salió mal
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-8">
              {errorMessage}
            </p>

            {/* Detalles técnicos (solo DEV) */}
            {import.meta.env.DEV && errorDetails && (
              <details className="mb-6 text-left">
                <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600 dark:hover:text-gray-300 select-none mb-2">
                  Detalles técnicos
                </summary>
                <pre className="text-xs text-red-500 bg-red-50 dark:bg-red-950/30 rounded-lg p-3 overflow-auto max-h-48 whitespace-pre-wrap border border-red-200 dark:border-red-900">
                  {errorDetails}
                </pre>
              </details>
            )}

            {/* Acciones */}
            <div className="flex flex-col sm:flex-row gap-2 mb-6">
              <Button
                variant="outline"
                fullWidth
                leftIcon={<ArrowLeft size={16} />}
                onClick={() => navigate(-1)}
              >
                Volver
              </Button>
              <Button
                fullWidth
                leftIcon={<RefreshCw size={16} />}
                onClick={() => window.location.reload()}
              >
                Recargar
              </Button>
              <Button
                variant="outline"
                fullWidth
                leftIcon={<Home size={16} />}
                onClick={() => navigate('/dashboard')}
              >
                Inicio
              </Button>
            </div>

            {/* Soporte */}
            <p className="text-xs text-gray-400 dark:text-gray-500">
              Si el problema persiste,{' '}
              <a href="/soporte" className="text-brand-600 dark:text-brand-400 hover:underline">
                contacta al soporte
              </a>
              .
            </p>

          </div>
        </div>
      </div>
    </div>
  )
}
