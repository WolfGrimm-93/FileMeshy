/**
 * navigation — puente de navegación imperativa (SPA) fuera de componentes React.
 *
 * Zustand stores, servicios y callbacks de toast NO pueden usar el hook `useNavigate`.
 * App.tsx registra aquí el `navigate` del data-router (createBrowserRouter) al arrancar,
 * y cualquier código no-React llama `navigateTo(path)` para navegar sin recargar la página.
 *
 * Si por algún motivo no se registró (tests, orden de carga), cae a `window.location`
 * como último recurso — la navegación ocurre igual, solo que con recarga completa.
 */

type NavigateFn = (to: string) => void

let navigateFn: NavigateFn | null = null

/** Registra la función de navegación del router. Llamado una vez desde App.tsx. */
export function setNavigate(fn: NavigateFn): void {
  navigateFn = fn
}

/** Navega a `to` usando el router (SPA); cae a window.location si no hay router registrado. */
export function navigateTo(to: string): void {
  if (navigateFn) {
    navigateFn(to)
  } else if (typeof window !== 'undefined') {
    window.location.assign(to)
  }
}
