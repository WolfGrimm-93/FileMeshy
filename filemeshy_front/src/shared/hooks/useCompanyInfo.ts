import { useConfig } from '@/modules/configuration/hooks/useConfig'
import { type CompanyConfig } from '@/modules/configuration/services/config.service'
import { logger, LogSection } from '@/shared/utils/logger'

const DEFAULT_COMPANY_INFO: CompanyConfig = {
  business_name: 'FileMeshy',
  legal_name: 'FileMeshy SRL',
  logo_path: null,
  logo_icon_path: null,
  primary_color: '#3A64D9',
  secondary_color: '#6552E0',
  phone: null,
  email: null,
  address: null,
  website: null,
  city: null,
  province: null,
  facebook: null,
  instagram: null,
  twitter: null,
  whatsapp_business: null,
}

/**
 * Hook para obtener información de la empresa
 * 
 * ⚠️ DEPRECADO: Usa el ConfigProvider que ya carga esta información
 * Esta es una capa de compatibilidad para mantener el código existente
 * 
 * El hook obtiene datos desde ConfigProvider (que ya hace el fetch)
 * en lugar de hacer su propia llamada, evitando duplicación de requests
 * 
 * Para nuevo código, usar directamente:
 * import { useConfig } from '@/modules/configuration/hooks/useConfig'
 * const { config } = useConfig()
 * 
 * @returns CompanyConfig | null - Información de la empresa desde BD
 */
export function useCompanyInfo() {
  const { config, isLoading } = useConfig()

  // Si la config está cargada, retornar la sección 'company'
  if (config) {
    return config.company
  }

  // Si hay error o no está cargado, retornar default
  if (!isLoading) {
    logger.warning(
      LogSection.SYSTEM,
      'useCompanyInfo: usando configuración predeterminada'
    )
  }

  return DEFAULT_COMPANY_INFO
}
