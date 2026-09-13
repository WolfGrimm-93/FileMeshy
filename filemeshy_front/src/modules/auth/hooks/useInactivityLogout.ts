/**
 * Hook de auto-logout por inactividad y duración máxima de sesión.
 * - inactivityMinutes: cierra sesión si no hay actividad (mouse, teclado, touch, scroll)
 * - maxSessionMinutes: cierra sesión pasado ese tiempo desde el login (independiente de actividad)
 */

import { useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

const ACTIVITY_EVENTS = ['mousedown', 'keydown', 'touchstart', 'scroll'] as const

export function useInactivityLogout(
  inactivityMinutes: number = 30,
  maxSessionHours: number = 8,
) {
  const navigate = useNavigate()
  const logout = useAuthStore(s => s.logout)
  const isAuthenticated = useAuthStore(s => s.isAuthenticated)
  const inactivityTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const sessionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleLogout = useCallback(() => {
    logout()
    navigate('/login', { replace: true })
  }, [logout, navigate])

  // Timer de inactividad — se reinicia con cada interacción
  const resetInactivityTimer = useCallback(() => {
    if (inactivityTimerRef.current) clearTimeout(inactivityTimerRef.current)
    if (inactivityMinutes > 0 && isAuthenticated) {
      inactivityTimerRef.current = setTimeout(handleLogout, inactivityMinutes * 60 * 1000)
    }
  }, [inactivityMinutes, isAuthenticated, handleLogout])

  useEffect(() => {
    if (!isAuthenticated) return

    // Inactividad
    if (inactivityMinutes > 0) {
      resetInactivityTimer()
      const handler = () => resetInactivityTimer()
      for (const event of ACTIVITY_EVENTS) {
        window.addEventListener(event, handler, { passive: true })
      }
      // Cleanup inactividad
      const cleanupInactivity = () => {
        if (inactivityTimerRef.current) clearTimeout(inactivityTimerRef.current)
        for (const event of ACTIVITY_EVENTS) {
          window.removeEventListener(event, handler)
        }
      }

      // Duración máxima de sesión — no se reinicia
      if (maxSessionHours > 0) {
        sessionTimerRef.current = setTimeout(handleLogout, maxSessionHours * 60 * 60 * 1000)
      }

      return () => {
        cleanupInactivity()
        if (sessionTimerRef.current) clearTimeout(sessionTimerRef.current)
      }
    }

    // Solo duración máxima (sin inactividad)
    if (maxSessionHours > 0) {
      sessionTimerRef.current = setTimeout(handleLogout, maxSessionHours * 60 * 60 * 1000)
      return () => {
        if (sessionTimerRef.current) clearTimeout(sessionTimerRef.current)
      }
    }
  }, [isAuthenticated, inactivityMinutes, maxSessionHours, resetInactivityTimer, handleLogout])
}
