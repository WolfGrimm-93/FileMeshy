import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './assets/index.css'
import 'sonner/dist/styles.css'
import { ThemeProvider } from './app/providers/ThemeProvider'
import { cleanupOldStorage } from './shared/utils/cleanup-storage'
import { Toaster } from 'sonner'
import './shared/utils/logger-helpers'
import { initConfig } from './shared/config/env'

async function bootstrap() {
  // Limpiar datos antiguos de localStorage antes de iniciar
  cleanupOldStorage()

  // Calcula la URL del API contra el dominio actual en prod (.env en dev)
  await initConfig()

  // Importar App recien ACA (no arriba con el resto de los imports): App.tsx
  // crea el router con createBrowserRouter a nivel de modulo, y React Router
  // dispara los loaders de la ruta inicial (authLoader -> /auth/refresh)
  // apenas se crea el router -- no espera a que se monte <RouterProvider>.
  // Con un import estatico, ese primer refresh salia con la URL "de fabrica"
  // (VITE_API_URL grabada en el build) en vez de la real, porque initConfig()
  // todavia no habia corrido. Rompia cualquier dominio que comparta la misma
  // imagen pero no sea el primario (ej. alias de tenant en el stack cloud).
  const { default: App } = await import('./App.tsx')

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ThemeProvider>
        <Toaster
          position="top-right"
          expand={true}
          duration={3000}
          gap={8}
        />
        <App />
      </ThemeProvider>
    </StrictMode>
  )
}

bootstrap()

// Remover splash cuando la app esté lista (no inmediatamente al render)
window.__removeSplash = () => {
  const splash = document.getElementById('splash')
  if (splash) {
    splash.style.opacity = '0'
    setTimeout(() => splash.remove(), 200)
  }
}

declare global {
  interface Window { __removeSplash?: () => void }
}
