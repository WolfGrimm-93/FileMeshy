/**
 * Página 404 — No encontrada
 */
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, LayoutDashboard } from 'lucide-react'
import { Button } from '@/ui/buttons/Button'
import { useEffect, useState } from 'react'

const QUICK_LINKS = [
  { to: '/archivos', label: 'Mis Archivos' },
  { to: '/notificaciones', label: 'Notificaciones' },
  { to: '/preferencias', label: 'Preferencias' },
]

export default function NotFoundPage() {
  const navigate = useNavigate()
  const [countdown, setCountdown] = useState(10)

  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          navigate('/dashboard')
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [navigate])

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
        <div className="w-full max-w-sm text-center">

          {/* Número grande */}
          <p className="text-[140px] font-black leading-none select-none text-brand-500/15 dark:text-brand-400/10 mb-2">
            404
          </p>

          {/* Título y descripción */}
          <h1 className="text-2xl font-bold text-foreground mb-2">
            Página no encontrada
          </h1>
          <p className="text-sm text-muted-foreground mb-1">
            La ruta que buscas no existe o fue movida.
          </p>
          <p className="text-sm text-muted-foreground mb-8">
            Redirigiendo en{' '}
            <span className="font-bold text-brand-500 tabular-nums">{countdown}</span>
            {' '}seg...
          </p>

          {/* Acciones */}
          <div className="flex gap-3 mb-8">
            <Button
              variant="outline"
              fullWidth
              leftIcon={<ArrowLeft className="h-4 w-4" />}
              onClick={() => navigate(-1)}
            >
              Volver
            </Button>
            <Button
              fullWidth
              leftIcon={<LayoutDashboard className="h-4 w-4" />}
              onClick={() => navigate('/dashboard')}
            >
              Inicio
            </Button>
          </div>

          {/* Accesos rápidos */}
          <div className="border-t border-border pt-6">
            <p className="text-xs text-muted-foreground mb-3">Accesos rápidos</p>
            <div className="flex flex-wrap gap-x-4 gap-y-2 justify-center">
              {QUICK_LINKS.map(({ to, label }) => (
                <Link
                  key={to}
                  to={to}
                  className="text-sm text-primary hover:underline"
                >
                  {label}
                </Link>
              ))}
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}
