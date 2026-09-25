/**
 * Contexto de configuración pública. Vive aparte de ConfigProvider.tsx para que
 * ese archivo exporte solo componentes (react-refresh / fast refresh).
 */
import { createContext } from 'react'
import type { PublicConfig } from '../services/config.service'

export interface ConfigContextType {
  config: PublicConfig | null
  isLoading: boolean
  error: Error | null
  refreshConfig: () => Promise<void>
}

export const ConfigContext = createContext<ConfigContextType | undefined>(undefined)
