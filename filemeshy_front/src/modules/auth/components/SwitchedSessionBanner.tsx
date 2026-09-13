import { useState } from 'react'
import { ArrowLeftRight, Loader2 } from 'lucide-react'
import { toast } from '@/ui/toast/CustomToast'
import { useAuth } from '@/modules/auth/hooks/useAuth'

/**
 * Franja visible mientras hay una sesion pausada por "Cambiar de usuario"
 * (ver SwitchUserModal / useAuth.switchUser). Se renderiza siempre que haya
 * algo pausado, en toda ruta -- para que nunca quede escondido el camino de
 * vuelta.
 */
export default function SwitchedSessionBanner() {
  const { pausedUsers, returnToPreviousUser } = useAuth()
  const [returning, setReturning] = useState(false)

  if (pausedUsers.length === 0) return null

  const previous = pausedUsers[pausedUsers.length - 1]
  const previousName = `${previous.first_name} ${previous.last_name}`.trim()

  const handleReturn = async () => {
    setReturning(true)
    try {
      const ok = await returnToPreviousUser()
      if (ok) toast.success(`Volviste a ${previousName}`)
    } finally {
      setReturning(false)
    }
  }

  return (
    <div className="shrink-0 bg-blue-600 dark:bg-blue-800 text-white text-sm px-4 py-2 flex items-center justify-between gap-3">
      <span>
        Sesión temporal activa — <strong>{previousName}</strong> quedó pausado
      </span>
      <button
        onClick={handleReturn}
        disabled={returning}
        className="flex items-center gap-1.5 px-3 py-1 bg-white/15 hover:bg-white/25 rounded-lg font-semibold transition disabled:opacity-60"
      >
        {returning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ArrowLeftRight className="w-3.5 h-3.5" />}
        Volver a {previous.first_name}
      </button>
    </div>
  )
}
