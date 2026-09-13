/**
 * PÁGINA: INICIO DE SESIÓN
 * Autenticación de usuarios con OAuth 2.0
 */

import { LoginForm } from '@/modules/auth/components'
import { MeshBackground } from '@/modules/auth/components/MeshBackground'
import '@/modules/auth/login.css'

export const LoginPage = () => {
  // La redirección si ya está autenticado se maneja en publicLoader (loaders.ts)
  // No necesita guard aquí — el loader bloquea el render antes de llegar a este componente

  return (
    <div className="filemeshy-login-scope min-h-screen w-full overflow-hidden relative">
      <MeshBackground />

      {/* Contenido principal */}
      <div className="relative z-10 flex min-h-screen items-center justify-center p-4 sm:p-6 md:p-8">
        <div className="w-full max-w-md">
          <LoginForm />
        </div>
      </div>
    </div>
  )
}
