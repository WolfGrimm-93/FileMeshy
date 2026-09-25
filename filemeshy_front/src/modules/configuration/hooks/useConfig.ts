import { useContext } from 'react'
import { ConfigContext } from '../providers/configContext'

export type { ConfigContextType } from '../providers/configContext'

export const useConfig = () => {
  const context = useContext(ConfigContext)
  if (context === undefined) {
    throw new Error('useConfig debe ser usado dentro de ConfigProvider')
  }
  return context
}
