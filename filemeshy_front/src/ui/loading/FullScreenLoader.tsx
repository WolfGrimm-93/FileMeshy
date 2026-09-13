/**
 * Loader de pantalla completa — un solo componente para toda la app.
 * Se usa como fallback de Suspense, splash screen, y carga inicial.
 */

interface FullScreenLoaderProps {
  message?: string
}

export function FullScreenLoader({ message = 'Cargando...' }: FullScreenLoaderProps) {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand-500 mx-auto mb-4" />
        <p className="text-muted-foreground">{message}</p>
      </div>
    </div>
  )
}
