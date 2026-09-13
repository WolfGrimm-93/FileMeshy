/**
 * PÁGINA: RESTABLECER CONTRASEÑA
 * 
 * 🔐 FLUJO SEGURO DE 3 PASOS:
 * 
 * PASO 1 (email):
 *   - Input: Email del usuario
 *   - Backend: Genera código, envía por email, guarda HASH en BD
 *   - Cookie: password_reset_session (opaco, UUID)
 * 
 * PASO 2 (code):
 *   - Input: Código de 6 dígitos (enviado por email)
 *   - Backend: Valida contra HASH, invalida código, genera reset_token JWT
 *   - Respuesta: reset_token (JWT con TTL 5 min)
 * 
 * PASO 3 (confirm):
 *   - Input: Nueva contraseña
 *   - Backend: Valida reset_token, cambia password, invalida token
 *   - Respuesta: success
 * 
 * SEGURIDAD:
 * - Email: localStorage (persistencia UX, no sensible)
 * - Código: NUNCA guardado (solo en memoria durante ingreso)
 * - reset_token: SOLO en memoria (NO en cookies/localStorage)
 */

import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, Mail, Key, Lock } from 'lucide-react'
import { Button } from '@/ui/buttons/Button'
import { Card, CardContent, CardHeader } from '@/ui/cards/Card'
import { EmailInput, PasswordInput, Input } from '@/ui/inputs'
import { toast } from '@/ui/toast/CustomToast'
import { passwordResetService, PASSWORD_RESET_ERROR_CODES } from '@/modules/auth/services/password-reset.service'

type ResetStep = 'email' | 'code' | 'confirm' | 'success'

// ===== STORAGE HELPERS =====
const RESET_EMAIL_STORAGE = 'filemeshy_reset_password_email_temp'

const getStoredEmail = (): string => {
  try {
    return localStorage.getItem(RESET_EMAIL_STORAGE) || ''
  } catch {
    return ''
  }
}

const saveEmailToStorage = (email: string) => {
  try {
    if (email.trim()) {
      localStorage.setItem(RESET_EMAIL_STORAGE, email)
    } else {
      localStorage.removeItem(RESET_EMAIL_STORAGE)
    }
  } catch {
    // Ignorar errores
  }
}

const clearEmailStorage = () => {
  try {
    localStorage.removeItem(RESET_EMAIL_STORAGE)
  } catch {
    // Ignorar errores
  }
}

export const ResetPassword = () => {
  const navigate = useNavigate()
  
  // ===== ESTADO GENERAL =====
  const [step, setStep] = useState<ResetStep>('email')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [expiresAt, setExpiresAt] = useState<Date | null>(null)
  const [timeRemaining, setTimeRemaining] = useState<string>('')
  const [sessionExpired, setSessionExpired] = useState(false)
  
  // ===== PASO 1: EMAIL =====
  const [email, setEmail] = useState(getStoredEmail())
  
  // ===== PASO 2: CODE =====
  const [code, setCode] = useState('')  // SOLO MEMORIA
  
  // ===== PASO 3: CONFIRM (nueva password) =====
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  
  // Guardar email en localStorage
  useEffect(() => {
    saveEmailToStorage(email)
  }, [email])
  
  // Timer para countdown
  useEffect(() => {
    if (!expiresAt || step !== 'code') return

    const interval = setInterval(() => {
      const now = new Date()
      const diff = expiresAt.getTime() - now.getTime()

      if (diff <= 0) {
        setTimeRemaining('Expirado')
        setSessionExpired(true)
        
        // Mostrar error y limpiar
        toast.error('Tu sesión ha expirado. Por favor, intenta de nuevo desde el inicio')
        
        // Limpiar estados
        setStep('email')
        setEmail('')
        setCode('')
        setNewPassword('')
        setConfirmPassword('')
        clearEmailStorage()
        
        // Redirigir a home después de 2 segundos
        const timeout = setTimeout(() => {
          navigate('/')
        }, 2000)
        
        clearInterval(interval)
        return () => clearTimeout(timeout)
      }

      const minutes = Math.floor(diff / 60000)
      const seconds = Math.floor((diff % 60000) / 1000)
      setTimeRemaining(`${minutes}:${seconds.toString().padStart(2, '0')}`)
    }, 1000)

    return () => clearInterval(interval)
  }, [expiresAt, step, navigate])
  
  // Auto-submit cuando el código tiene exactamente 6 dígitos
  useEffect(() => {
    if (step === 'code' && code.length === 6 && !isLoading && !sessionExpired) {
      handleVerifyCode({ preventDefault: () => {} } as React.FormEvent)
    }
  }, [code]) // eslint-disable-line react-hooks/exhaustive-deps
  
  // ===== HANDLER PASO 1: Solicitar Código =====
  const handleRequestCode = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)

    try {
      if (!email.trim()) {
        toast.error('Por favor ingresa tu correo electrónico')
        setIsLoading(false)
        return
      }

      if (!passwordResetService.validateEmail(email)) {
        toast.error('El correo electrónico no es válido')
        setIsLoading(false)
        return
      }

      // PASO 1: POST /password-reset/request
      const response = await passwordResetService.requestPasswordReset(email)

      // Calcular tiempo de expiración
      const expires = new Date()
      expires.setMinutes(expires.getMinutes() + (response.expires_in_minutes || 15))
      setExpiresAt(expires)
      setTimeRemaining(`${response.expires_in_minutes || 15}:00`)

      toast.success('Código enviado. Revisa tu correo electrónico')
      setCode('')  // Limpiar
      setStep('code')  // Avanzar a PASO 2
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Error desconocido'
      toast.error(`Error: ${errorMessage}`)
    } finally {
      setIsLoading(false)
    }
  }

  // ===== HANDLER PASO 2: Verificar Código =====
  const handleVerifyCode = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)

    try {
      if (!passwordResetService.validateCode(code)) {
        toast.error('El código debe contener exactamente 6 dígitos')
        setIsLoading(false)
        return
      }

      // PASO 2: POST /password-reset/verify (reset_token llega por cookie httpOnly)
      await passwordResetService.verifyCode(code)

      toast.success('Código verificado. Establece tu nueva contraseña')
      setCode('')  // Limpiar código de memoria
      setStep('confirm')  // Avanzar a PASO 3
    } catch (err) {
      // Extraer código y mensaje del error
      let errorCode = ''
      let errorMessage = 'Código inválido'
      
      if (err instanceof Error) {
        errorMessage = err.message
        // El mensaje contiene ahora: "code: message" o solo el código
        // Intentar extraer el código
        if (errorMessage.includes(':')) {
          const parts = errorMessage.split(':')
          errorCode = parts[0].trim()
          errorMessage = parts.slice(1).join(':').trim()
        }
      }
      
      // Detectar códigos de error específicos
      const isSessionError = 
        errorCode === PASSWORD_RESET_ERROR_CODES.SESSION_NOT_FOUND ||
        errorCode === PASSWORD_RESET_ERROR_CODES.SESSION_EXPIRED ||
        errorCode === PASSWORD_RESET_ERROR_CODES.MAX_ATTEMPTS_EXCEEDED ||
        errorCode === PASSWORD_RESET_ERROR_CODES.CODE_EXPIRED ||
        errorMessage.includes(PASSWORD_RESET_ERROR_CODES.SESSION_NOT_FOUND) ||
        errorMessage.includes(PASSWORD_RESET_ERROR_CODES.SESSION_EXPIRED) ||
        errorMessage.includes(PASSWORD_RESET_ERROR_CODES.MAX_ATTEMPTS_EXCEEDED) ||
        errorMessage.includes(PASSWORD_RESET_ERROR_CODES.CODE_EXPIRED)
      
      if (isSessionError) {
        toast.error('Tu sesión ha expirado o llegaste al máximo de intentos. Por favor, solicita un nuevo código')
        
        // Limpiar TODO
        setEmail('')
        setCode('')
        setNewPassword('')
        setConfirmPassword('')
        setStep('email')
        clearEmailStorage()
        
        // Redirigir a home después de 2 segundos
        setTimeout(() => {
          navigate('/')
        }, 2000)
      } else {
        toast.error(errorMessage)
      }
    } finally {
      setIsLoading(false)
    }
  }

  // ===== HANDLER PASO 3: Confirmar Contraseña =====
  const handleConfirmPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    // Validar que las contraseñas coincidan
    if (newPassword !== confirmPassword) {
      toast.error('Las contraseñas no coinciden')
      return
    }

    // Validar complejidad
    const passwordValidation = passwordResetService.validatePassword(newPassword)
    if (!passwordValidation.valid) {
      toast.error(passwordValidation.error || 'Contraseña no válida')
      return
    }

    setIsLoading(true)

    try {
      // PASO 3: POST /password-reset/confirm (reset_token viene por cookie httpOnly)
      await passwordResetService.confirmPasswordReset(newPassword)

      toast.success('Contraseña actualizada exitosamente')

      // Limpiar todo
      setEmail('')
      setCode('')
      setNewPassword('')
      setConfirmPassword('')
      clearEmailStorage()

      setStep('success')

      // Redirigir a login después de 3 segundos
      setTimeout(() => {
        navigate('/login')
      }, 3000)
    } catch (err) {
      // Extraer código y mensaje del error
      let errorCode = ''
      let errorMessage = 'Error desconocido'
      
      if (err instanceof Error) {
        errorMessage = err.message
        // El mensaje contiene ahora: "code: message" o solo el código
        // Intentar extraer el código
        if (errorMessage.includes(':')) {
          const parts = errorMessage.split(':')
          errorCode = parts[0].trim()
          errorMessage = parts.slice(1).join(':').trim()
        }
      }
      
      // Detectar códigos de error específicos que requieren limpiar todo
      const isSessionError = 
        errorCode === PASSWORD_RESET_ERROR_CODES.TOKEN_EXPIRED ||
        errorCode === PASSWORD_RESET_ERROR_CODES.TOKEN_ALREADY_USED ||
        errorCode === PASSWORD_RESET_ERROR_CODES.USER_NOT_FOUND ||
        errorCode === PASSWORD_RESET_ERROR_CODES.INVALID_TOKEN ||
        errorMessage.includes(PASSWORD_RESET_ERROR_CODES.TOKEN_EXPIRED) ||
        errorMessage.includes(PASSWORD_RESET_ERROR_CODES.TOKEN_ALREADY_USED) ||
        errorMessage.includes(PASSWORD_RESET_ERROR_CODES.USER_NOT_FOUND) ||
        errorMessage.includes(PASSWORD_RESET_ERROR_CODES.INVALID_TOKEN)
      
      if (isSessionError) {
        toast.error('Tu sesión ha expirado. Por favor, solicita un nuevo código')
        
        // Limpiar TODO
        setEmail('')
        setCode('')
        setNewPassword('')
        setConfirmPassword('')
        setStep('email')
        clearEmailStorage()

        // Redirigir a home después de 2 segundos
        setTimeout(() => {
          navigate('/')
        }, 2000)
      } else {
        toast.error(errorMessage)
      }
    } finally {
      setIsLoading(false)
    }
  }

  // ======== PASO 1: Solicitar código ========
  if (step === 'email') {
    return (
      <div className="min-h-screen w-full overflow-hidden relative bg-linear-to-br from-gray-50 via-brand-50/30 to-gray-50 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
        {/* Patrón de fondo decorativo */}
        <div className="absolute inset-0 overflow-hidden">
          {/* Grid sutil */}
          <div
            className="absolute inset-0 opacity-[0.03] dark:opacity-[0.05]"
            style={{
              backgroundImage: `
                linear-gradient(to right, currentColor 1px, transparent 1px),
                linear-gradient(to bottom, currentColor 1px, transparent 1px)
              `,
              backgroundSize: '60px 60px'
            }}
          />

          {/* Círculos decorativos */}
          <div className="absolute -top-24 -left-24 w-96 h-96 bg-brand-500/10 dark:bg-brand-500/5 rounded-full blur-3xl" />
          <div className="absolute -bottom-24 -right-24 w-96 h-96 bg-brand-500/10 dark:bg-brand-500/5 rounded-full blur-3xl" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-linear-to-br from-brand-500/5 to-transparent dark:from-brand-500/3 rounded-full blur-3xl" />
        </div>

        {/* Contenido principal */}
        <div className="relative flex min-h-screen items-center justify-center p-4 sm:p-6 md:p-8">
          <div className="w-full max-w-md">
            <Card variant="elevated" padding="xl" shadow="2xl" rounded="2xl" className="w-full backdrop-blur-xs">
              <CardHeader className="space-y-6 pb-8">
                <div className="flex justify-center">
                  <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-linear-to-br from-brand-500 to-brand-600 shadow-lg">
                    <Mail className="h-8 w-8 text-white" />
                  </div>
                </div>
                <div className="space-y-2 text-center">
                  <h1 className="text-3xl font-bold tracking-tight text-foreground">
                    Restablecer contraseña
                  </h1>
                  <p className="text-sm text-muted-foreground">
                    Te enviaremos un código a tu correo
                  </p>
                </div>
              </CardHeader>

              <CardContent className="px-8 pb-8">
                <form onSubmit={handleRequestCode} className="space-y-6">
                  <div className="space-y-4">
                    <EmailInput
                      value={email}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                        setEmail(e.target.value)
                        setError('')
                      }}
                      placeholder="tu@email.com"
                      required
                    />

                    {error && (
                      <div className="rounded-lg bg-red-50 dark:bg-red-900/20 p-4 border border-red-200 dark:border-red-800">
                        <p className="text-sm text-red-800 dark:text-red-400">
                          {error}
                        </p>
                      </div>
                    )}

                    <div className="rounded-lg bg-blue-50 dark:bg-blue-900/20 p-4 border border-blue-200 dark:border-blue-800">
                      <p className="text-xs text-blue-800 dark:text-blue-400">
                        ℹ️ El código de verificación expira en 15 minutos. Revisa tu carpeta de spam si no lo recibes.
                      </p>
                    </div>
                  </div>

                  <Button
                    type="submit"
                    disabled={isLoading || !email}
                    variant="primary"
                    size="lg"
                    buttonStyle="solid"
                    fullWidth
                    isLoading={isLoading}
                    loadingText="Enviando..."
                    leftIcon={!isLoading ? <Mail className="size-5" /> : undefined}
                    shadow="md"
                  >
                    Enviar código
                  </Button>
                </form>

                <div className="mt-6 pt-6 border-t border-border">
                  <div className="text-center text-sm text-muted-foreground">
                    ¿Recordaste tu contraseña?{' '}
                    <Link
                      to="/login"
                      onClick={clearEmailStorage}
                      className="text-brand-600 hover:text-primary dark:hover:text-brand-300 font-medium transition-colors"
                    >
                      Volver al inicio
                    </Link>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    )
  }

  // ======== PASO 2: Verificar código ========
  if (step === 'code') {
    return (
      <div className="min-h-screen w-full overflow-hidden relative bg-linear-to-br from-gray-50 via-brand-50/30 to-gray-50 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
        {/* Patrón de fondo decorativo */}
        <div className="absolute inset-0 overflow-hidden">
          {/* Grid sutil */}
          <div
            className="absolute inset-0 opacity-[0.03] dark:opacity-[0.05]"
            style={{
              backgroundImage: `
                linear-gradient(to right, currentColor 1px, transparent 1px),
                linear-gradient(to bottom, currentColor 1px, transparent 1px)
              `,
              backgroundSize: '60px 60px'
            }}
          />

          {/* Círculos decorativos */}
          <div className="absolute -top-24 -left-24 w-96 h-96 bg-brand-500/10 dark:bg-brand-500/5 rounded-full blur-3xl" />
          <div className="absolute -bottom-24 -right-24 w-96 h-96 bg-brand-500/10 dark:bg-brand-500/5 rounded-full blur-3xl" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-linear-to-br from-brand-500/5 to-transparent dark:from-brand-500/3 rounded-full blur-3xl" />
        </div>

        {/* Contenido principal */}
        <div className="relative flex min-h-screen items-center justify-center p-4 sm:p-6 md:p-8">
          <div className="w-full max-w-md">
            <Card variant="elevated" padding="xl" shadow="2xl" rounded="2xl" className="w-full backdrop-blur-xs">
              <CardHeader className="space-y-6 pb-8">
                <div className="flex items-center justify-between">
                  <button
                    onClick={() => {
                      // Limpiar TODO y redirija a home
                      setStep('email')
                      setCode('')
                      setEmail('')

                      setNewPassword('')
                      setConfirmPassword('')
                      setExpiresAt(null)
                      clearEmailStorage()
                      
                      // Redirigir a home
                      navigate('/')
                    }}
                    className="flex h-10 w-10 items-center justify-center rounded-lg hover:bg-muted transition-colors"
                    title="Cancelar y volver al inicio"
                  >
                    <ArrowLeft className="h-5 w-5 text-muted-foreground" />
                  </button>
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-linear-to-br from-blue-500 to-blue-600 shadow-lg">
                    <Key className="h-6 w-6 text-white" />
                  </div>
                  <div className="w-10" /> {/* Spacer for alignment */}
                </div>
                <div className="space-y-2 text-center">
                  <h1 className="text-3xl font-bold tracking-tight text-foreground">
                    Verifica el código
                  </h1>
                  <p className="text-sm text-muted-foreground">
                    Ingresa el código enviado a {email}
                  </p>
                </div>
              </CardHeader>

              <CardContent className="px-8 pb-8">
                <form onSubmit={handleVerifyCode} className="space-y-6">
                  <div className="space-y-4">
                    {timeRemaining && (
                      <div className={`rounded-lg p-4 border ${
                        timeRemaining === 'Expirado'
                          ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                          : 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800'
                      }`}>
                        <p className={`text-sm font-medium ${
                          timeRemaining === 'Expirado'
                            ? 'text-red-800 dark:text-red-400'
                            : 'text-blue-800 dark:text-blue-400'
                        }`}>
                          ⏱️ Código expira en: <span className="font-mono font-bold">{timeRemaining}</span>
                        </p>
                      </div>
                    )}

                    <Input
                      type="text"
                      placeholder="123456"
                      value={code}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                        const value = e.target.value.replace(/\D/g, '').slice(0, 6)
                        setCode(value)
                        setError('')
                      }}
                      maxLength={6}
                      variant="outlined"
                      size={3}
                      className="text-center text-2xl tracking-widest font-mono"
                      required
                    />

                    {error && (
                      <div className="rounded-lg bg-red-50 dark:bg-red-900/20 p-4 border border-red-200 dark:border-red-800">
                        <p className="text-sm text-red-800 dark:text-red-400">
                          {error}
                        </p>
                      </div>
                    )}

                    <div className="rounded-lg bg-blue-50 dark:bg-blue-900/20 p-4 border border-blue-200 dark:border-blue-800">
                      <p className="text-xs text-blue-800 dark:text-blue-400">
                        ℹ️ Ingresa el código de 6 dígitos enviado a tu correo
                      </p>
                    </div>
                  </div>

                  <Button
                    type="submit"
                    disabled={isLoading || code.length !== 6}
                    variant="primary"
                    size="lg"
                    buttonStyle="solid"
                    fullWidth
                    isLoading={isLoading}
                    loadingText="Verificando..."
                    leftIcon={!isLoading ? <Key className="size-5" /> : undefined}
                    shadow="md"
                  >
                    Verificar código
                  </Button>
                </form>

                <div className="mt-6 pt-6 border-t border-border">
                  <div className="text-center text-sm text-muted-foreground">
                    ¿No recibiste el código?{' '}
                    <button
                      onClick={() => handleRequestCode({ preventDefault: () => {} } as React.FormEvent)}
                      className="text-brand-600 hover:text-primary dark:hover:text-brand-300 font-medium transition-colors"
                    >
                      Reenviar código
                    </button>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    )
  }

// ======== PASO 3: Confirmar Nueva Contraseña ========
  if (step === 'confirm') {
    return (
      <div className="min-h-screen w-full overflow-hidden relative bg-linear-to-br from-gray-50 via-brand-50/30 to-gray-50 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
        {/* Patrón de fondo decorativo */}
        <div className="absolute inset-0 overflow-hidden">
          <div
            className="absolute inset-0 opacity-[0.03] dark:opacity-[0.05]"
            style={{
              backgroundImage: `
                linear-gradient(to right, currentColor 1px, transparent 1px),
                linear-gradient(to bottom, currentColor 1px, transparent 1px)
              `,
              backgroundSize: '60px 60px'
            }}
          />
          <div className="absolute -top-24 -left-24 w-96 h-96 bg-brand-500/10 dark:bg-brand-500/5 rounded-full blur-3xl" />
          <div className="absolute -bottom-24 -right-24 w-96 h-96 bg-brand-500/10 dark:bg-brand-500/5 rounded-full blur-3xl" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-linear-to-br from-brand-500/5 to-transparent dark:from-brand-500/3 rounded-full blur-3xl" />
        </div>

        {/* Contenido principal */}
        <div className="relative flex min-h-screen items-center justify-center p-4 sm:p-6 md:p-8">
          <div className="w-full max-w-md">
            <Card variant="elevated" padding="xl" shadow="2xl" rounded="2xl" className="w-full backdrop-blur-xs">
              <CardHeader className="space-y-6 pb-8">
                <div className="flex items-center justify-between">
                  <button
                    onClick={() => {
                      // Limpiar TODO y redirija a home
                      setStep('email')
                      setCode('')
                      setEmail('')

                      setNewPassword('')
                      setConfirmPassword('')
                      setExpiresAt(null)
                      clearEmailStorage()
                      
                      // Redirigir a home
                      navigate('/')
                    }}
                    className="flex h-10 w-10 items-center justify-center rounded-lg hover:bg-muted transition-colors"
                    title="Cancelar y volver al inicio"
                  >
                    <ArrowLeft className="h-5 w-5 text-muted-foreground" />
                  </button>
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-linear-to-br from-purple-500 to-purple-600 shadow-lg">
                    <Lock className="h-6 w-6 text-white" />
                  </div>
                  <div className="w-10" />
                </div>
                <div className="space-y-2 text-center">
                  <h1 className="text-3xl font-bold tracking-tight text-foreground">
                    Nueva contraseña
                  </h1>
                  <p className="text-sm text-muted-foreground">
                    Elige una contraseña segura
                  </p>
                </div>
              </CardHeader>

              <CardContent className="px-8 pb-8">
                <form onSubmit={handleConfirmPassword} className="space-y-6">
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-foreground/80 mb-2">
                        Nueva contraseña
                      </label>
                      <PasswordInput
                        value={newPassword}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                          setNewPassword(e.target.value)
                          setError('')
                        }}
                        placeholder="••••••••"
                        required
                      />
                      {newPassword && (() => {
                        const checks = [
                          newPassword.length >= 8,
                          /[A-Z]/.test(newPassword),
                          /[a-z]/.test(newPassword),
                          /\d/.test(newPassword),
                        ]
                        const score = checks.filter(Boolean).length
                        const labels = ['', 'Débil', 'Regular', 'Buena', 'Fuerte']
                        const colors = ['', 'bg-red-500', 'bg-yellow-500', 'bg-blue-500', 'bg-green-500']
                        const textColors = ['', 'text-red-600 dark:text-red-400', 'text-yellow-600 dark:text-yellow-400', 'text-blue-600 dark:text-blue-400', 'text-green-600 dark:text-green-400']
                        return (
                          <div className="mt-2 space-y-1">
                            <div className="flex gap-1">
                              {[1,2,3,4].map(i => (
                                <div key={i} className={`h-1 flex-1 rounded-full transition-all ${i <= score ? colors[score] : 'bg-gray-200 dark:bg-gray-700'}`} />
                              ))}
                            </div>
                            <div className="flex justify-between items-center">
                              <span className={`text-xs font-medium ${textColors[score]}`}>{labels[score]}</span>
                              <span className="text-xs text-gray-400">{checks.filter(Boolean).length}/4 requisitos</span>
                            </div>
                          </div>
                        )
                      })()}
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-foreground/80 mb-2">
                        Confirmar contraseña
                      </label>
                      <PasswordInput
                        value={confirmPassword}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                          setConfirmPassword(e.target.value)
                          setError('')
                        }}
                        placeholder="••••••••"
                        required
                      />
                    </div>

                    {error && (
                      <div className="rounded-lg bg-red-50 dark:bg-red-900/20 p-4 border border-red-200 dark:border-red-800">
                        <p className="text-sm text-red-800 dark:text-red-400">{error}</p>
                      </div>
                    )}

                    <div className="rounded-lg bg-blue-50 dark:bg-blue-900/20 p-4 border border-blue-200 dark:border-blue-800">
                      <p className="text-xs text-blue-800 dark:text-blue-400">
                        Requisitos: mínimo 8 caracteres, mayúscula, minúscula y número
                      </p>
                    </div>
                  </div>

                  <Button
                    type="submit"
                    disabled={isLoading || !newPassword || !confirmPassword}
                    variant="primary"
                    size="lg"
                    buttonStyle="solid"
                    fullWidth
                    isLoading={isLoading}
                    loadingText="Guardando..."
                    leftIcon={!isLoading ? <Lock className="size-5" /> : undefined}
                    shadow="md"
                  >
                    Guardar contraseña
                  </Button>
                </form>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    )
  }

  // ======== ÉXITO ========
  return (
    <div className="min-h-screen w-full overflow-hidden relative bg-linear-to-br from-gray-50 via-brand-50/30 to-gray-50 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
      {/* Patrón de fondo decorativo */}
      <div className="absolute inset-0 overflow-hidden">
        <div
          className="absolute inset-0 opacity-[0.03] dark:opacity-[0.05]"
          style={{
            backgroundImage: `
              linear-gradient(to right, currentColor 1px, transparent 1px),
              linear-gradient(to bottom, currentColor 1px, transparent 1px)
            `,
            backgroundSize: '60px 60px'
          }}
        />
        <div className="absolute -top-24 -left-24 w-96 h-96 bg-green-500/10 dark:bg-green-500/5 rounded-full blur-3xl" />
        <div className="absolute -bottom-24 -right-24 w-96 h-96 bg-green-500/10 dark:bg-green-500/5 rounded-full blur-3xl" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-linear-to-br from-green-500/5 to-transparent dark:from-green-500/3 rounded-full blur-3xl" />
      </div>

      {/* Contenido principal */}
      <div className="relative flex min-h-screen items-center justify-center p-4 sm:p-6 md:p-8">
        <div className="w-full max-w-md">
          <Card variant="elevated" padding="xl" shadow="2xl" rounded="2xl" className="w-full backdrop-blur-xs">
            <CardHeader className="space-y-6 pb-8">
              <div className="flex justify-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-linear-to-br from-green-500 to-green-600 shadow-lg">
                  <CheckCircle2 className="h-8 w-8 text-white" />
                </div>
              </div>
              <div className="space-y-2 text-center">
                <h1 className="text-3xl font-bold tracking-tight text-foreground">
                  ¡Contraseña actualizada!
                </h1>
                <p className="text-sm text-muted-foreground">
                  Tu contraseña ha sido restablecida exitosamente
                </p>
              </div>
            </CardHeader>

            <CardContent className="px-8 pb-8">
              <div className="space-y-4 text-center">
                <p className="text-foreground/80">
                  Ya puedes iniciar sesión con tu nueva contraseña
                </p>
                <Button
                  onClick={() => navigate('/login')}
                  variant="primary"
                  size="lg"
                  buttonStyle="solid"
                  fullWidth
                  shadow="md"
                >
                  Ir al inicio de sesión
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

