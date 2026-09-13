/**
 * ConfigProvider - Carga la configuración pública al iniciar la app
 * 
 * Se ejecuta UNA SOLA VEZ antes de renderizar cualquier componente
 */

import { useEffect, useState, useCallback, useRef, type ReactNode } from 'react'
import { configService, type PublicConfig } from '../services/config.service'
import { adminConfigurationService } from '../services/admin-configuration.service'
import { useAuth } from '@/modules/auth/hooks/useAuth'

// R5: intervalo de polling de la versión global de config (multi-terminal).
// El aviso viejo (localStorage + evento `storage`) solo llega entre pestañas del
// MISMO navegador -- nunca entre computadoras distintas.
const CONFIG_VERSION_POLL_MS = 25_000

export interface ConfigContextType {
  config: PublicConfig | null
  isLoading: boolean
  error: Error | null
  refreshConfig: () => Promise<void>
}

import { createContext, useContext } from 'react'

const ConfigContext = createContext<ConfigContextType | undefined>(undefined)

export interface ConfigProviderProps {
  children: ReactNode
}

export const ConfigProvider = ({ children }: ConfigProviderProps) => {
  const [config, setConfig] = useState<PublicConfig | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    const loadConfig = async () => {
      try {
        const loadedConfig = await configService.getPublicConfig()
        setConfig(loadedConfig)
      } catch (err) {
        const error = err instanceof Error ? err : new Error(String(err))
        setError(error)
        console.error('❌ Error cargando configuración:', error)
      } finally {
        setIsLoading(false)
      }
    }

    loadConfig()
  }, [])

  const refreshConfig = useCallback(async () => {
    configService.clearCache()
    try {
      const fresh = await configService.getPublicConfig()
      setConfig(fresh)
    } catch {
      // mantener config anterior si falla el refresh
    }
  }, [])

  // `configService` es un singleton de módulo, sin scope de tenant -- en modo cloud, cada
  // login puede caer en un tenant distinto (mismo dominio/pestaña, sin recarga de página), y
  // sin este efecto seguía mostrando el logo/RNC/config del tenant anterior hasta que algo
  // más disparara un refresh (bug real encontrado 2026-08-11: el logo de un tenant aparecía
  // en otro después de cambiar de sesión en la misma pestaña). Se refresca cada vez que
  // cambia el usuario autenticado -- cubre login, cambio de cuenta y restauración de sesión.
  const { user } = useAuth()
  const userId = user?.id ?? null
  const previousUserId = useRef<string | null | undefined>(undefined)

  useEffect(() => {
    if (previousUserId.current === undefined) {
      previousUserId.current = userId
      return
    }
    if (userId !== previousUserId.current) {
      previousUserId.current = userId
      if (userId) {
        refreshConfig()
      }
    }
  }, [userId, refreshConfig])

  // R5: polling de la versión global de config -- detecta cambios hechos desde
  // OTRA terminal/computadora (el evento `storage` de localStorage solo avisa
  // entre pestañas del mismo navegador). null = todavía no se estableció la
  // primera lectura, para no disparar un refresh espurio justo al cargar.
  const lastSeenVersion = useRef<number | null>(null)

  useEffect(() => {
    const poll = async () => {
      let version: number
      try {
        version = await adminConfigurationService.getConfigVersion()
      } catch {
        return // sin sesión activa o error de red -- se reintenta en el próximo tick
      }

      if (lastSeenVersion.current === null) {
        lastSeenVersion.current = version
        return
      }
      if (version === lastSeenVersion.current) return

      lastSeenVersion.current = version
      await refreshConfig()

      // Avisar a los hooks que ya escuchan el evento `storage` (useFiscalConfig,
      // usePOSConfig, useSeguridadConfig, useFacturaFiscalConfig, etc.) sin tener
      // que tocar cada uno. Un StorageEvent disparado a mano SÍ llega a la pestaña
      // actual (a diferencia del evento nativo entre pestañas, que la salta) --
      // por eso alcanza con esto para notificar TODA la pestaña de esta terminal.
      const stamp = String(Date.now())
      try {
        localStorage.setItem('filemeshy_config_updated', stamp)
      } catch {
        // localStorage no disponible (modo privado, cuota llena, etc.) -- no crítico
      }
      window.dispatchEvent(new StorageEvent('storage', { key: 'filemeshy_config_updated', newValue: stamp }))
    }

    // Establecer la línea base YA, no esperar al primer tick del interval (25s
    // después) -- si el cambio en OTRA terminal ocurre en esa ventana, la primera
    // lectura real lo tomaría como si fuera el estado inicial y nunca dispararía
    // el refresh.
    poll()

    const interval = setInterval(poll, CONFIG_VERSION_POLL_MS)
    return () => clearInterval(interval)
  }, [refreshConfig])

  return (
    <ConfigContext.Provider value={{ config, isLoading, error, refreshConfig }}>
      {children}
    </ConfigContext.Provider>
  )
}

export const useConfig = () => {
  const context = useContext(ConfigContext)
  if (context === undefined) {
    throw new Error('useConfig debe ser usado dentro de ConfigProvider')
  }
  return context
}

