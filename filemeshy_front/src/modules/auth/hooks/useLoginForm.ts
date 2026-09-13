/**
 * Hook personalizado para gestión del formulario de login
 * Maneja validaciones, estado del formulario y lógica de autenticación
 */
import { useState, useRef, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from './useAuth'
import { toast } from '@/ui/toast/CustomToast'
import { authService } from '../services/auth.service'
import type { TurnstileConfig } from '../services/auth.service'
import { getTenantSlug, setTenantSlug } from '@/shared/config/env'

/** True si la página corre en dominio público (no local) */
function detectRequiresTurnstile(): boolean {
  if (typeof window === 'undefined') return false
  const host = window.location.hostname
  return !/^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)/.test(host) && host !== ''
}

interface FormData {
  email: string
  password: string
  tenantSlug: string
}

interface FieldErrors {
  email: string
  password: string
}

type LoginStep = 'credentials' | 'totp'

export const useLoginForm = () => {
  const navigate = useNavigate()
  const { login } = useAuth()

  // Referencias para los inputs
  const emailInputRef = useRef<HTMLInputElement>(null)
  const passwordInputRef = useRef<HTMLInputElement>(null)

  // Estado del formulario
  const [formData, setFormData] = useState<FormData>({
    email: '',
    password: '',
    // Precargado con el ultimo tenant usado (persistido en localStorage) --
    // solo relevante cuando env.tenantSelectorEnabled muestra el campo.
    tenantSlug: getTenantSlug(),
  })

  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({
    email: '',
    password: '',
  })

  // Estado de Turnstile
  const requiresTurnstile = detectRequiresTurnstile()
  const [turnstileConfig, setTurnstileConfig] = useState<TurnstileConfig | null>(null)
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null)

  useEffect(() => {
    if (!requiresTurnstile) return
    authService.getTurnstileConfig()
      .then(cfg => setTurnstileConfig(cfg))
      .catch(() => setTurnstileConfig({ enabled: false, site_key: '' }))
  }, [requiresTurnstile])

  // Estado del paso 2FA
  const [loginStep, setLoginStep] = useState<LoginStep>('credentials')
  const [preAuthToken, setPreAuthToken] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const totpInputRef = useRef<HTMLInputElement>(null)

  /**
   * Valida que el email tenga un formato válido
   * Usa una regex robusta para verificar emails reales
   */
  const isValidEmail = (email: string): boolean => {
    // Regex completa para validar emails según RFC 5322 (simplificada)
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    
    if (!emailRegex.test(email)) return false
    
    // No permitir puntos consecutivos
    if (email.includes('..')) return false
    
    // No permitir múltiples @
    if (email.split('@').length !== 2) return false
    
    // Verificar que el dominio tenga al menos un punto
    const [, domain] = email.split('@')
    if (!domain || !domain.includes('.')) return false
    
    // Verificar que no empiece o termine con punto
    if (email.startsWith('.') || email.endsWith('.')) return false
    
    // Verificar que la parte local no esté vacía
    const [localPart] = email.split('@')
    if (!localPart || localPart.length === 0) return false
    
    // Verificar que la extensión del dominio tenga al menos 2 caracteres
    const domainParts = domain.split('.')
    const tld = domainParts[domainParts.length - 1]
    if (!tld || tld.length < 2) return false
    
    return true
  }

  /**
   * Valida un campo individual del formulario
   */
  const validateField = useCallback((fieldName: keyof FormData, value: string): string => {
    switch (fieldName) {
      case 'email': {
        const trimmedEmail = value.trim()
        
        if (!trimmedEmail) {
          return 'El correo electrónico es requerido'
        }
        
        if (!isValidEmail(trimmedEmail)) {
          return 'Ingresa un correo electrónico válido (ej: usuario@dominio.com)'
        }
        
        return ''
      }
      
      case 'password': {
        if (!value) {
          return 'La contraseña es requerida'
        }
        
        if (value.length < 6) {
          return 'La contraseña debe tener al menos 6 caracteres'
        }
        
        return ''
      }
      
      default:
        return ''
    }
  }, [])

  /**
   * Valida el formulario completo antes del envío
   * Retorna true si es válido, false si hay errores
   */
  const validateForm = useCallback((): FieldErrors => {
    const errors: FieldErrors = {
      email: validateField('email', formData.email),
      password: validateField('password', formData.password),
    }

    setFieldErrors(errors)

    // Mostrar toast del primer error encontrado
    if (errors.email) {
      toast.error(errors.email, { duration: 3000 })
    } else if (errors.password) {
      toast.error(errors.password, { duration: 3000 })
    }

    return errors
  }, [formData, validateField])

  /**
   * Maneja cambios en los campos del formulario
   * Incluye validación en tiempo real opcional
   */
  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    
    // Actualizar el valor del campo
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }))
    
    // Limpiar el error del campo cuando el usuario empieza a escribir
    setFieldErrors((prev) => ({
      ...prev,
      [name]: '',
    }))
    
    // Limpiar el error general
    if (error) {
      setError('')
    }
  }, [error])

  /**
   * Maneja la validación cuando el usuario sale del campo (onBlur)
   * Esto proporciona feedback inmediato sin ser intrusivo
   */
  const handleBlur = useCallback((fieldName: keyof FormData) => {
    const value = formData[fieldName]
    const fieldError = validateField(fieldName, value)
    
    if (fieldError) {
      setFieldErrors((prev) => ({
        ...prev,
        [fieldName]: fieldError,
      }))
    }
  }, [formData, validateField])

  /**
   * Alterna la visibilidad de la contraseña
   */
  const togglePasswordVisibility = useCallback(() => {
    setShowPassword((prev) => !prev)
  }, [])

  /**
   * Maneja el envío del formulario
   */
  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    
    // Limpiar errores previos
    setError('')

    // Validar formulario — usar errores frescos retornados directamente (evita fieldErrors stale)
    const errors = validateForm()
    if (errors.email || errors.password) {
      if (errors.email && emailInputRef.current) {
        emailInputRef.current.focus()
      } else if (errors.password && passwordInputRef.current) {
        passwordInputRef.current.focus()
      }
      return
    }

    // Bloquear si Turnstile está habilitado y aún no hay token
    if (requiresTurnstile && turnstileConfig?.enabled && !turnstileToken) {
      toast.error('Completa la verificación CAPTCHA antes de continuar', { duration: 3000 })
      return
    }

    // Multi-tenancy (fase 2): fija el tenant elegido ANTES de llamar a login()
    // -- axios.ts lo lee de acá para el header X-Tenant-Slug de esta y todas
    // las llamadas siguientes (incluido el refresh de sesión al recargar).
    setTenantSlug(formData.tenantSlug)

    setIsLoading(true)

    try {
      const result = await login({
        email: formData.email.trim().toLowerCase(),
        password: formData.password,
        remember_me: rememberMe,
        turnstile_token: turnstileToken ?? undefined,
      })

      // Si el backend pide 2FA, cambiar al paso TOTP
      if (result && 'requires_2fa' in result && result.requires_2fa) {
        setPreAuthToken(result.pre_auth_token)
        setLoginStep('totp')
        setTotpCode('')
        setTimeout(() => totpInputRef.current?.focus(), 100)
        return
      }

      toast.dismiss()
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      // Manejo robusto de errores del backend
      let errorMessage = 'Error al iniciar sesión. Por favor verifica tus credenciales.'

      // Caso 1: Error con respuesta del servidor (axios)
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosError = err as { 
          response?: { 
            data?: { 
              detail?: string | string[]
              message?: string 
            }
            status?: number
          } 
        }
        
        const detail = axiosError.response?.data?.detail
        const message = axiosError.response?.data?.message
        const status = axiosError.response?.status

        // Priorizar el mensaje 'detail' que viene del backend
        if (typeof detail === 'string') {
          errorMessage = detail
        } else if (Array.isArray(detail) && detail.length > 0) {
          errorMessage = detail[0]
        } else if (message) {
          errorMessage = message
        }

        // Mensajes específicos según el código de error
        if (status === 401) {
          // Ya tenemos el mensaje del backend (credenciales incorrectas o cuenta desactivada)
        } else if (status === 500) {
          errorMessage = 'Error en el servidor. Por favor intenta más tarde.'
        } else if (status === 422) {
          errorMessage = 'Datos inválidos. Verifica el formato del email.'
        } else if (status === 0 || !status) {
          errorMessage = 'No se puede conectar al servidor. Verifica tu conexión.'
        }
      } 
      // Caso 2: Error de JavaScript nativo
      else if (err instanceof Error) {
        errorMessage = err.message
      }
      
      // Mostrar error como toast con efecto glassmorphism
      toast.error(errorMessage, { duration: 3000 })
      
      console.error('❌ Error al iniciar sesión:', err)

      // Limpiar campos del formulario
      setFormData((prev) => ({
        email: '',
        password: '',
        tenantSlug: prev.tenantSlug,
      }))

      // Enfocar el campo de email para facilitar la corrección
      if (emailInputRef.current) {
        emailInputRef.current.focus()
      }
    } finally {
      setIsLoading(false)
    }
  }, [formData, login, navigate, validateForm])

  const handleTotpSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (totpCode.length < 6) return
    setIsLoading(true)
    try {
      const result = await authService.verifyTwoFactorLogin(preAuthToken, totpCode)

      // Completar login en el store
      const { useAuthStore } = await import('../store/authStore')
      const u = result.user
      useAuthStore.getState().login({ ...u, permissions: new Set(u.permissions) })
      toast.dismiss()
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      let msg = 'Código incorrecto'
      if (err && typeof err === 'object' && 'response' in err) {
        const e = err as { response?: { data?: { detail?: string } } }
        msg = e.response?.data?.detail || msg
      }
      toast.error(msg)
      setTotpCode('')
      totpInputRef.current?.focus()
    } finally {
      setIsLoading(false)
    }
  }, [totpCode, preAuthToken, navigate])

  const cancelTotp = useCallback(() => {
    setLoginStep('credentials')
    setPreAuthToken('')
    setTotpCode('')
    setFormData((prev) => ({ email: '', password: '', tenantSlug: prev.tenantSlug }))
  }, [])

  return {
    // Estado
    formData,
    showPassword,
    isLoading,
    error,
    fieldErrors,
    rememberMe,
    setRememberMe,
    loginStep,
    totpCode,
    setTotpCode,

    // Turnstile
    turnstileConfig,
    turnstileToken,
    setTurnstileToken,

    // Referencias
    emailInputRef,
    passwordInputRef,
    totpInputRef,

    // Funciones
    handleChange,
    handleBlur,
    togglePasswordVisibility,
    handleSubmit,
    handleTotpSubmit,
    cancelTotp,
    setError,
  }
}