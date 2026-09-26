import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Users, X } from 'lucide-react'
import { Button } from '@/ui/buttons'
import { EmailInput, PasswordInput } from '@/ui/inputs/Input'
import { toast } from '@/ui/toast/CustomToast'
import { useAuth } from '@/modules/auth/hooks/useAuth'

interface SwitchUserModalProps {
  isOpen: boolean
  onClose: () => void
}

/**
 * Login liviano para "Cambiar de usuario" -- a diferencia de LoginForm/
 * useLoginForm (pensados para la pantalla publica /login), este pausa la
 * sesion activa en vez de reemplazarla, y no navega a ningun lado: el que
 * lo abre ya esta autenticado y adentro de la app.
 *
 * No soporta 2FA (ver switchUser en useAuth.ts) ni Turnstile -- ambos
 * pensados para el login publico anonimo; esta accion ya requiere una
 * sesion activa, no aplica el mismo riesgo de bots.
 */
export default function SwitchUserModal({ isOpen, onClose }: SwitchUserModalProps) {
  const { switchUser } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const emailInputRef = useRef<HTMLInputElement>(null)

  // Ajuste de estado durante el render: al pasar a abierto se limpia el formulario
  const [prevOpen, setPrevOpen] = useState(isOpen)
  if (isOpen !== prevOpen) {
    setPrevOpen(isOpen)
    if (isOpen) {
      setEmail('')
      setPassword('')
      setError('')
    }
  }

  // Foco en el email al abrir
  useEffect(() => {
    if (!isOpen) return
    const timer = setTimeout(() => emailInputRef.current?.focus(), 50)
    return () => clearTimeout(timer)
  }, [isOpen])

  if (!isOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password) return
    setLoading(true)
    setError('')
    try {
      const response = await switchUser({ email: email.trim().toLowerCase(), password })
      toast.success(`Sesión temporal iniciada como ${response.user.first_name}`)
      onClose()
    } catch (err: unknown) {
      let message = 'No se pudo iniciar sesión'
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosError = err as { response?: { data?: { detail?: string; message?: string } } }
        message = axiosError.response?.data?.detail || axiosError.response?.data?.message || message
      } else if (err instanceof Error) {
        message = err.message
      }
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  return createPortal(
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-card rounded-2xl shadow-2xl max-w-sm w-full border border-border animate-fadeIn">
        <div className="p-5 border-b border-border flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center shrink-0">
              <Users className="text-blue-500" size={20} />
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground">Cambiar de usuario</h3>
              <p className="text-xs text-muted-foreground">Tu sesión actual queda pausada, no se pierde nada</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground shrink-0"
            title="Cancelar"
          >
            <X size={18} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 flex flex-col gap-3">
          <div>
            <label className="text-xs text-muted-foreground mb-1 block" htmlFor="switch-user-1">Correo</label>
            <EmailInput id="switch-user-1"
              ref={emailInputRef}
              value={email}
              onChange={e => { setEmail(e.target.value); setError('') }}
              placeholder="usuario@empresa.com"
              variant="outlined"
              fullWidth
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block" htmlFor="switch-user-2">Contraseña</label>
            <PasswordInput id="switch-user-2"
              value={password}
              onChange={e => { setPassword(e.target.value); setError('') }}
              variant="outlined"
              fullWidth
            />
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
          <div className="flex gap-3 pt-2">
            <Button type="button" variant="secondary" fullWidth onClick={onClose}>Cancelar</Button>
            <Button type="submit" variant="primary" fullWidth isLoading={loading} disabled={!email.trim() || !password}>
              Entrar
            </Button>
          </div>
        </form>
      </div>
    </div>,
    document.body
  )
}
