/**
 * Proveedor de autenticación
 * Se encarga de restaurar la sesión al cargar la aplicación
 */
import { useEffect, useState, useRef } from 'react'
import type { ReactNode } from 'react'
import { authService } from '../services/auth.service'
import { useAuthStore } from '../store/authStore'
import fileMeshyLogo from '@/assets/images/logo-filemeshy-color.png'

interface AuthProviderProps {
  children: ReactNode
}

export const AuthProvider = ({ children }: AuthProviderProps) => {
  const [isRestoring, setIsRestoring] = useState(true)
  const hasRestored = useRef(false)
  useAuthStore(state => state.login)
  const setLogout = useAuthStore(state => state.logout)
  const markInitialized = useAuthStore(state => state.markInitialized)

  useEffect(() => {
    // Prevenir múltiples restauraciones
    if (hasRestored.current) return

    const restore = async () => {
      try {
        hasRestored.current = true
        
        // Rutas públicas que NO requieren restauración de sesión
        const publicRoutes = ['/login', '/register', '/reset-password', '/public', '/about', '/terms', '/privacy', '/soporte']
        const currentPath = window.location.pathname
        const isPublicRoute = publicRoutes.some(route => currentPath.startsWith(route))
        
        // Si es ruta pública, no restaurar sesión
        if (isPublicRoute) {
          console.log('📄 Ruta pública detectada:', currentPath, '- Omitiendo restauración de sesión')
          markInitialized()
          setIsRestoring(false)
          return
        }
        
        // IMPORTANTE: Solo restaurar sesión (refrescar token con cookie)
        // NO llamar getCurrentUser() aquí - el authLoader lo hará en el router
        const restored = await authService.restoreSession()
        
        // Marcar como inicializado (authLoader lo completará con getCurrentUser)
        markInitialized()
        
        if (restored) {
          console.log('✅ Sesión restaurada (token refrescado con cookie)')
        } else {
          console.log('ℹ️ No hay sesión para restaurar')
          setLogout()
        }
      } catch (error) {
        console.error('Error restaurando sesión:', error)
        setLogout()
      } finally {
        // Pequeño delay para que la animación de salida termine antes de desmontar
        setTimeout(() => setIsRestoring(false), 350)
      }
    }

    restore()
    // Solo ejecutar una vez al montar
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])  // Cambié dependencias: quitar setLogin, setLogout (son estables)

  // Splash screen mientras se restaura la sesión
  if (isRestoring) {
    return (
      <div
        className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 bg-background"
        style={{ animation: 'splashFadeOut 0.3s ease-out 0.05s both' }}
      >
        <style>{`
          @keyframes splashFadeOut {
            from { opacity: 1; }
            to   { opacity: 0; }
          }
          @keyframes splashDot {
            0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
            40%            { transform: scale(1);   opacity: 1;   }
          }
        `}</style>
        <img
          src={fileMeshyLogo}
          alt="FileMeshy"
          className="h-14 w-auto object-contain opacity-90"
        />
        <div className="flex gap-2">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="block h-2 w-2 rounded-full bg-primary"
              style={{ animation: `splashDot 1.2s ease-in-out ${i * 0.2}s infinite` }}
            />
          ))}
        </div>
      </div>
    )
  }

  return <>{children}</>
}
