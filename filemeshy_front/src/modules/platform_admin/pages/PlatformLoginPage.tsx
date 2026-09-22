/**
 * PÁGINA: LOGIN DEL PANEL DE PLATAFORMA
 *
 * Panel completamente separado del login/RBAC normal de la app -- se
 * autentica con un secreto compartido (`X-Platform-Key`), no con un usuario.
 * Solo alcanzable tipeando la URL (`/plataforma/login`), fuera de
 * Sidebar/Navbar/rutas normales (ver decisión de arquitectura en el
 * contrato de la Ronda 8).
 *
 * No hay endpoint de "verificar key" dedicado: se valida pegándola y
 * llamando a `tenants.service.list()` -- si responde 200, la key es válida.
 */
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck, LogIn } from 'lucide-react'
import { Button } from '@/ui/buttons/Button'
import { PasswordInput } from '@/ui/inputs/Input'
import { usePlatformAuthStore } from '../store/platformAuthStore'
import { tenantsService } from '../services/tenants.service'
import { getPlatformErrorStatus } from '../services/platformAdmin.api'

export default function PlatformLoginPage() {
  const navigate = useNavigate()
  const setKey = usePlatformAuthStore((s) => s.setKey)
  const clearKey = usePlatformAuthStore((s) => s.clearKey)

  const [keyInput, setKeyInput] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!keyInput.trim() || isSubmitting) return

    setIsSubmitting(true)
    setError(null)

    // Guardar la key ANTES de probarla -- el interceptor de request de
    // platformAdmin.api.ts la lee de sessionStorage, no hay forma de mandarla
    // "de prueba" sin persistirla primero. Si falla, se limpia abajo.
    setKey(keyInput.trim())

    try {
      await tenantsService.list()
      navigate('/plataforma/tenants')
    } catch (err) {
      const statusCode = getPlatformErrorStatus(err)
      if (statusCode === 429) {
        setError('Demasiados intentos, esperá unos minutos antes de volver a intentar.')
      } else if (statusCode === undefined) {
        // Sin status HTTP -- axios no llegó a recibir respuesta (backend
        // caído, timeout, red cortada, etc.). Sin este caso separado, un
        // 401 y un servidor inalcanzable mostraban el mismo "Clave
        // incorrecta.", que manda al operador a revisar la key cuando el
        // problema real es de conectividad.
        setError('No se pudo conectar al servidor. Probá de nuevo en un momento.')
      } else if (statusCode >= 500) {
        setError('Error del servidor, probá de nuevo en un momento.')
      } else {
        setError('Clave incorrecta.')
      }
      clearKey()
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex size-12 items-center justify-center rounded-full bg-brand-600/20 text-brand-400">
            <ShieldCheck className="size-6" />
          </div>
          <h1 className="text-xl font-bold text-white">Panel de Plataforma</h1>
          <p className="mt-1 text-sm text-gray-400">
            Administración de tenants -- acceso restringido por clave de operador
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-lg border border-gray-800 bg-gray-900 p-6 shadow-lg"
        >
          <label htmlFor="platform-key" className="mb-2 block text-sm font-medium text-gray-300">
            Clave de plataforma
          </label>
          <PasswordInput
            id="platform-key"
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            placeholder="X-Platform-Key"
            error={error ?? undefined}
            autoComplete="off"
            autoFocus
          />

          <Button
            type="submit"
            variant="primary"
            fullWidth
            className="mt-4"
            isLoading={isSubmitting}
            loadingText="Verificando..."
            leftIcon={<LogIn className="size-4" />}
            disabled={!keyInput.trim()}
          >
            Entrar
          </Button>
        </form>
      </div>
    </div>
  )
}
