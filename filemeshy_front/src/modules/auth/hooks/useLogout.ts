/**
 * Hook useLogout
 * Proporciona funcionalidad de logout con confirmación opcional y manejo de errores
 */

import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from './useAuth'

interface UseLogoutOptions {
  /**
   * Mostrar confirmación antes de cerrar sesión
   */
  withConfirmation?: boolean
  
  /**
   * Mensaje de confirmación personalizado
   */
  confirmationMessage?: string
  
  /**
   * Título del diálogo de confirmación
   */
  confirmationTitle?: string
  
  /**
   * Ruta a la que redirigir después del logout
   */
  redirectTo?: string
  
  /**
   * Callback que se ejecuta antes del logout
   */
  onBeforeLogout?: () => void | Promise<void>
  
  /**
   * Callback que se ejecuta después del logout exitoso
   */
  onSuccess?: () => void
  
  /**
   * Callback que se ejecuta si hay un error
   */
  onError?: (error: Error) => void
}

interface UseLogoutReturn {
  /**
   * Función para ejecutar el logout
   */
  handleLogout: () => Promise<void>
  
  /**
   * Estado de loading durante el logout
   */
  isLoggingOut: boolean
  
  /**
   * Error si ocurrió durante el logout
   */
  error: Error | null
  
  /**
   * Estado del diálogo de confirmación
   */
  showConfirmDialog: boolean
  
  /**
   * Función para confirmar el logout
   */
  confirmLogout: () => Promise<void>
  
  /**
   * Función para cancelar el logout
   */
  cancelLogout: () => void
  
  /**
   * Título del diálogo de confirmación
   */
  confirmationTitle: string
  
  /**
   * Mensaje del diálogo de confirmación
   */
  confirmationMessage: string
}

export function useLogout(options: UseLogoutOptions = {}): UseLogoutReturn {
  const {
    withConfirmation = false,
    confirmationMessage = '¿Estás seguro que deseas cerrar sesión?',
    confirmationTitle = 'Cerrar Sesión',
    redirectTo = '/login',
    onBeforeLogout,
    onSuccess,
    onError,
  } = options

  const navigate = useNavigate()
  const { logout } = useAuth()
  const [isLoggingOut, setIsLoggingOut] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [showConfirmDialog, setShowConfirmDialog] = useState(false)

  const confirmLogout = useCallback(async () => {
    try {
      setIsLoggingOut(true)
      setError(null)
      setShowConfirmDialog(false)

      // Ejecutar callback antes del logout
      if (onBeforeLogout) {
        await onBeforeLogout()
      }

      console.log('🔑 Iniciando cierre de sesión...')

      // Ejecutar logout
      await logout()

      console.log('✅ Sesión cerrada exitosamente')

      // Ejecutar callback de éxito
      if (onSuccess) {
        onSuccess()
      }

      navigate(redirectTo, { replace: true })
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Error desconocido al cerrar sesión')
      console.error('❌ Error al cerrar sesión:', error)

      setError(error)

      if (onError) {
        onError(error)
      }

      // Aún así redirigir a login por seguridad
      navigate(redirectTo, { replace: true })
    } finally {
      setIsLoggingOut(false)
    }
  }, [onBeforeLogout, logout, onSuccess, navigate, redirectTo, onError])

  const cancelLogout = useCallback(() => {
    setShowConfirmDialog(false)
  }, [])

  const handleLogout = useCallback(async () => {
    // Prevenir múltiples clicks
    if (isLoggingOut) return

    // Mostrar confirmación si está habilitada
    if (withConfirmation) {
      setShowConfirmDialog(true)
      return
    }

    // Ejecutar logout directamente si no hay confirmación
    await confirmLogout()
  }, [isLoggingOut, withConfirmation, confirmLogout])

  return {
    handleLogout,
    isLoggingOut,
    error,
    showConfirmDialog,
    confirmLogout,
    cancelLogout,
    confirmationTitle: confirmationTitle,
    confirmationMessage: confirmationMessage,
  }
}
