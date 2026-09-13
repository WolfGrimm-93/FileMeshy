import { useState } from 'react'
import { Building2, Phone, Mail, Globe, MapPin, Tag } from 'lucide-react'
import logoIconColor from '../../../assets/logo-icon.png'
import { useSidebarStore } from '@/app/store/sidebarStore'
import { useConfig } from '@/modules/configuration/hooks/useConfig'
import { Modal } from '@/ui/modals/Modal'

interface BusinessInfo {
  nombre: string
  tipo: string
  imagen?: string
}

interface SidebarHeaderProps {
  business?: BusinessInfo
}

export default function SidebarHeader({
  business = {
    nombre: 'FileMeshy',
    tipo: 'Almacenamiento de Archivos',
  },
}: SidebarHeaderProps) {
  const [imageError, setImageError] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const { collapsed } = useSidebarStore()
  const { config } = useConfig()

  const company = config?.company
  const displayName = company?.business_name ?? business.nombre
  const appVersion = config?.app?.version

  return (
    <div className="flex flex-col items-center relative">
      {/* Logo */}
      <button
        type="button"
        onClick={() => setShowModal(true)}
        className={`relative group cursor-pointer transition-all duration-300 ${collapsed ? 'px-0 mt-2' : 'px-3 mt-2'}`}
        title="Ver información de la empresa"
      >
        {business.imagen && !imageError ? (
          <img
            src={business.imagen}
            alt={`Logo de ${displayName}`}
            className={`h-auto object-contain group-hover:scale-105 transition-all duration-300 ${collapsed ? 'w-10' : 'w-full max-h-24'}`}
            onError={() => setImageError(true)}
            loading="lazy"
          />
        ) : (
          <img
            src={logoIconColor}
            alt="FileMeshy"
            className={`h-auto object-contain group-hover:scale-105 transition-all duration-300 ${collapsed ? 'w-10' : 'w-full max-h-24'}`}
          />
        )}
      </button>

      {/* Nombre + tipo — oculto cuando está colapsado */}
      <div
        className={`text-center px-2 w-full mt-1 transition-all duration-300 overflow-hidden ${
          collapsed ? 'opacity-0 max-h-0 pointer-events-none' : 'opacity-100 max-h-16'
        }`}
      >
        <button
          type="button"
          onClick={() => setShowModal(true)}
          className="block w-full group"
          title="Ver información de la empresa"
        >
          <h1 className="text-lg font-bold text-gray-900 dark:text-white group-hover:text-brand-600 dark:group-hover:text-brand-400 transition-colors duration-300 truncate leading-tight">
            {displayName}
          </h1>
        </button>
        <p className="text-[11px] text-gray-600 dark:text-gray-400 truncate">
          {business.tipo}
        </p>
      </div>

      {/* Separador */}
      <div className={`w-full mt-2 transition-all duration-300 ${collapsed ? 'px-1' : 'px-4'}`}>
        <div className="relative">
          <div className="bg-gray-200 dark:bg-gray-800 h-px" />
          <div className="absolute inset-0 bg-linear-to-r from-transparent via-brand-500/50 to-transparent h-px" />
        </div>
      </div>

      {/* Modal de empresa */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title={displayName}
        size="sm"
      >
        <div className="space-y-3 -mt-1">
          {company?.legal_name && company.legal_name !== displayName && (
            <p className="text-sm text-muted-foreground -mt-2 mb-1">{company.legal_name}</p>
          )}
          {company?.phone && <InfoRow icon={Phone} label="Teléfono" value={company.phone} />}
          {company?.email && <InfoRow icon={Mail} label="Email" value={company.email} />}
          {company?.website && <InfoRow icon={Globe} label="Sitio web" value={company.website} />}
          {(company?.address || company?.city || company?.province) && (
            <InfoRow
              icon={MapPin}
              label="Dirección"
              value={[company.address, company.city, company.province].filter(Boolean).join(', ')}
            />
          )}
          {!company?.phone && !company?.email && (
            <div className="flex flex-col items-center py-4 gap-2">
              <Building2 className="w-8 h-8 text-gray-300 dark:text-gray-600" />
              <p className="text-sm text-muted-foreground">Sin información adicional configurada</p>
            </div>
          )}
          {appVersion && <InfoRow icon={Tag} label="Versión" value={`v${appVersion}`} />}
        </div>
      </Modal>
    </div>
  )
}

function InfoRow({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="flex items-start gap-3">
      <div className="w-7 h-7 rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center shrink-0 mt-0.5">
        <Icon className="w-3.5 h-3.5 text-gray-500 dark:text-gray-400" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-gray-500 dark:text-gray-400 leading-none mb-0.5">{label}</p>
        <p className="text-sm text-gray-900 dark:text-gray-100 font-medium wrap-break-word">{value}</p>
      </div>
    </div>
  )
}
