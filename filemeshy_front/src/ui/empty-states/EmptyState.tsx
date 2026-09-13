import React from 'react'
import { AlertCircle, Database } from 'lucide-react'

export interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  description: string
  primaryAction?: {
    label: string
    onClick: () => void
  }
  secondaryAction?: {
    label: string
    onClick: () => void
  }
  links?: Array<{
    label: string
    onClick: () => void
  }>
  className?: string
}

export function EmptyState({
  icon,
  title,
  description,
  primaryAction,
  secondaryAction,
  links,
  className = '',
}: EmptyStateProps) {
  return (
    <div className={`max-w-md text-center ${className}`}>
      <div className="mx-auto size-20 text-gray-400 dark:text-gray-600">
        {icon || <DefaultEmptyIcon />}
      </div>

      <h2 className="mt-6 text-2xl font-bold text-gray-900 dark:text-white">{title}</h2>

      <p className="mt-4 text-pretty text-gray-700 dark:text-gray-300">{description}</p>

      {(primaryAction || secondaryAction) && (
        <div className="mt-6 space-y-3">
          {primaryAction && (
            <button
              onClick={primaryAction.onClick}
              className="block w-full rounded-lg bg-brand-600 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-brand-700 focus:outline-hidden focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
            >
              {primaryAction.label}
            </button>
          )}

          {secondaryAction && (
            <button
              onClick={secondaryAction.onClick}
              className="block w-full rounded-lg border border-gray-300 bg-white px-6 py-3 text-sm font-medium text-gray-900 transition-colors hover:bg-gray-50 focus:outline-hidden focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 dark:border-gray-600 dark:bg-gray-800 dark:text-white dark:hover:bg-gray-700 dark:focus:ring-offset-gray-900"
            >
              {secondaryAction.label}
            </button>
          )}
        </div>
      )}

      {links && links.length > 0 && (
        <p className="mt-6 text-sm text-gray-700 dark:text-gray-400">
          {links.map((link, index) => (
            <React.Fragment key={index}>
              {index > 0 && ' o '}
              <button
                onClick={link.onClick}
                className="underline hover:text-gray-900 dark:hover:text-gray-200"
              >
                {link.label}
              </button>
            </React.Fragment>
          ))}
        </p>
      )}
    </div>
  )
}

// Empty states preconfigurados para casos comunes
export function NoDataState({ onImport, onCreate }: { onImport: () => void; onCreate: () => void }) {
  return (
    <EmptyState
      icon={<DatabaseIcon />}
      title="Sin datos para mostrar"
      description="Comienza importando datos existentes o creando nuevos registros."
      primaryAction={{
        label: 'Importar Datos',
        onClick: onImport,
      }}
      secondaryAction={{
        label: 'Crear Nuevo',
        onClick: onCreate,
      }}
      links={[{ label: 'Formatos soportados: CSV, JSON', onClick: () => {} }]}
    />
  )
}

// Iconos
function DefaultEmptyIcon() {
  return <AlertCircle className="size-full" />
}

function DatabaseIcon() {
  return <Database className="size-full" />
}
