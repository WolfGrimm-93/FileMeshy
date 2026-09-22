import { type ReactNode, useEffect } from 'react'
import Sidebar from './Sidebar/Sidebar'
import Navbar from './Navbar'
import SwitchedSessionBanner from '@/modules/auth/components/SwitchedSessionBanner'
import { useLogout } from '@/modules/auth/hooks/useLogout'
import { ConfirmDialog } from '@/ui'
import { useSidebarStore } from '@/app/store/sidebarStore'
// Panel flotante global de subidas grandes (multipart) -- ver comentario en el
// propio componente sobre por qué vive acá (fuera de FilesPage/UploadModal) y
// no dentro del árbol de /archivos: tiene que sobrevivir a cerrar el modal de
// subida y a navegar a otra página de la app.
import UploadsTray from '@/modules/files/components/UploadsTray'

interface MainLayoutProps {
  children: ReactNode
}

export default function MainLayout({ children }: MainLayoutProps) {
  const { setCollapsed } = useSidebarStore()

  // Auto-colapsar sidebar en pantallas pequeñas (<1024px)
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 1024) setCollapsed(true)
    }
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [setCollapsed])

  // Hook de logout con opciones personalizadas
  const { 
    handleLogout, 
    isLoggingOut, 
    showConfirmDialog, 
    confirmLogout, 
    cancelLogout,
    confirmationTitle,
    confirmationMessage 
  } = useLogout({
    withConfirmation: true,
    confirmationTitle: 'Cerrar Sesión',
    confirmationMessage: '¿Estás seguro que deseas cerrar sesión?',
    redirectTo: '/login',
    onBeforeLogout: async () => {
      console.log('🔄 Preparando cierre de sesión...')
      // Aquí puedes guardar datos pendientes, limpiar timers, etc.
    },
    onSuccess: () => {
      console.log('✨ Sesión cerrada correctamente')
    },
    onError: (error) => {
      console.error('⚠️ Error en logout:', error.message)
      // Aquí puedes mostrar una notificación al usuario
    }
  })

  return (
    <>
      <div className="flex flex-col h-screen overflow-hidden print:h-auto print:overflow-visible">
        {/* Banner de sesión temporal pausada — visible en toda ruta.
            print:hidden porque es chrome de navegación, no contenido -- ninguna página de
            la app debería imprimir el sidebar/navbar/banner detrás de lo que sea que se
            está imprimiendo (confirmado real: sin esto, un overlay position:fixed como
            PrintTokenPage.tsx no "tapa" este chrome al imprimir -- solo lo cubre
            visualmente en pantalla, el layout de abajo sigue en el flujo normal y
            aparece igual en el PDF/impresión). */}
        <div className="print:hidden">
          <SwitchedSessionBanner />
        </div>

        <div className="flex flex-1 overflow-hidden gap-2 p-2 sm:gap-3 sm:p-3 bg-gray-50 dark:bg-gray-950 print:overflow-visible print:gap-0 print:p-0">
          {/* Sidebar — flotante (separada del borde, redondeada, con blur); oculta al imprimir */}
          <div className="shrink-0 h-full print:hidden">
            <Sidebar />
          </div>

          {/* Main content area */}
          {/* max-[1024px]:min-w-0: sin esto, un hijo con contenido ancho (ej. una tabla)
              evita que este flex item se achique en pantallas chicas -- el contenido termina
              empujando la pagina entera en vez de scrollear adentro de su propia caja, y como
              el padre tiene overflow-hidden, ese excedente queda invisible ("se pierde"). */}
          <div className="flex-1 flex flex-col overflow-hidden gap-2 sm:gap-3 max-[1024px]:min-w-0 print:overflow-visible print:gap-0">
            {/* Navbar — flotante; oculto al imprimir */}
            <div className="shrink-0 print:hidden">
              <Navbar
                onLogout={handleLogout}
                isLoggingOut={isLoggingOut}
              />
            </div>

            {/* Page content - Scrollable */}
            <main className="flex-1 overflow-y-auto scrollbar-hide bg-gray-50 dark:bg-gray-950 transition-colors duration-300 max-[1024px]:min-w-0 p-6">
              <div className="w-full animate-fadeIn">
                {children}
              </div>
            </main>
          </div>
        </div>
      </div>

      {/* Panel flotante global de subidas grandes en curso/pausadas/procesando + banner de
          sesiones sin terminar detectadas en IndexedDB (ver UploadsTray.tsx) -- se auto-oculta
          cuando no hay nada que mostrar. */}
      <UploadsTray />

      {/* Diálogo de confirmación de logout */}
      <ConfirmDialog
        isOpen={showConfirmDialog}
        onClose={cancelLogout}
        onConfirm={confirmLogout}
        title={confirmationTitle}
        message={confirmationMessage}
        variant="warning"
        confirmText="Sí, cerrar sesión"
        cancelText="Cancelar"
      />
    </>
  )
}
