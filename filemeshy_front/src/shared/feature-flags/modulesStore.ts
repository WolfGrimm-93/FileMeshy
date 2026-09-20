import { create } from 'zustand'

/**
 * Estado de los módulos de negocio activables/desactivables.
 *
 * Hoy `FeaturesConfig` (config.service.ts) no trae ningún flag de módulo y
 * ConfigProvider no puebla este store. Se conserva el mecanismo genérico
 * (isModuleEnabled fail-open) porque `requireModule`/`requireModulePublic`
 * (app/routes/loaders.ts) todavía lo usan como factory reutilizable, aunque
 * ninguna ruta activa los llama por ahora.
 *
 * Se usa un store de Zustand (no el contexto de useConfig) porque
 * ModuleGuard corre dentro de loaders de react-router (app/routes/loaders.ts),
 * fuera del árbol de componentes -- igual que useAuthStore.getState() en
 * authLoader. Un contexto de React no se puede leer ahí.
 */
export interface ModulesState {
  modules: Record<string, boolean>
  loaded: boolean
  setModules: (modules: Record<string, boolean>) => void
  isModuleEnabled: (moduleKey: string) => boolean
}

export const useModulesStore = create<ModulesState>((set, get) => ({
  modules: {},
  loaded: false,
  setModules: (modules) => set({ modules, loaded: true }),
  // Fail-open: si el módulo no está cargado todavía o no viene en la respuesta,
  // no bloquea -- el enforcement real (403) vive en el backend de todas formas.
  isModuleEnabled: (moduleKey) => get().modules[moduleKey] !== false,
}))
