import type { ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  description?: string
  actions?: ReactNode
  icon?: ReactNode
  className?: string
}

export default function PageHeader({
  title,
  description,
  actions,
  icon,
  className = '',
}: PageHeaderProps) {
  return (
    <div className={`flex items-start justify-between gap-4 ${className}`}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-3">
          {icon && (
            <div className="shrink-0 w-12 h-12 rounded-xl bg-linear-to-br from-brand-500 to-brand-600 flex items-center justify-center text-white shadow-lg">
              {icon}
            </div>
          )}
          <div className="flex-1 min-w-0">
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white truncate">
              {title}
            </h1>
            {description && (
              <p className="mt-2 text-gray-600 dark:text-gray-400 line-clamp-2">
                {description}
              </p>
            )}
          </div>
        </div>
      </div>

      {actions && (
        <div className="shrink-0 flex items-center gap-2">
          {actions}
        </div>
      )}
    </div>
  )
}
