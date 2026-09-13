/**
 * Página 403 — Acceso denegado
 */
import { useNavigate } from 'react-router-dom'
import { ShieldX, ArrowLeft, LayoutDashboard } from 'lucide-react'
import { Button } from '@/ui/buttons/Button'
import { useAuth } from '@/modules/auth/hooks/useAuth'

const ROLE_LABELS: Record<string, string> = {
  SUPER_ADMIN: 'Super Administrador',
  ADMIN: 'Administrador',
  USER: 'Usuario',
}

export default function UnauthorizedPage() {
  const navigate = useNavigate()
  const { user } = useAuth()

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

          {/* Icono */}
          <div className="flex justify-center mb-6">
            <div className="w-20 h-20 rounded-2xl bg-red-500/10 dark:bg-red-500/10 flex items-center justify-center">
              <ShieldX className="w-10 h-10 text-red-500 dark:text-red-400" strokeWidth={1.5} />
            </div>
          </div>

          {/* Código y título */}
          <p className="text-xs font-semibold text-muted-foreground tracking-widest uppercase mb-2">
            Error 403
          </p>
          <h1 className="text-2xl font-bold text-foreground mb-2">
            Acceso denegado
          </h1>
          <p className="text-sm text-muted-foreground mb-8">
            No tienes permisos para acceder a esta sección.
            Si crees que es un error, contacta al administrador.
          </p>

          {/* Info del usuario */}
          {user && (
            <div className="bg-white/70 dark:bg-gray-800/60 backdrop-blur-xs border border-border rounded-xl p-4 mb-8 text-left space-y-2">
              <div className="flex items-center justify-between gap-4">
                <span className="text-xs text-muted-foreground shrink-0">Cuenta</span>
                <span className="text-xs font-medium text-foreground/80 truncate">
                  {user.email}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="text-xs text-muted-foreground shrink-0">Rol</span>
                <span className="text-xs font-medium text-foreground/80">
                  {ROLE_LABELS[user.role] ?? user.role}
                </span>
              </div>
            </div>
          )}

          {/* Acciones */}
          <div className="flex gap-3">
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

        </div>
      </div>
    </div>
  )
}
