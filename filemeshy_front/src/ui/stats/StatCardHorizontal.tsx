import React from 'react'

export interface StatCardHorizontalProps {
  label: string
  value: string | number
  trend?: 'up' | 'down'
  trendValue?: string
  icon?: React.ReactNode
  showIcon?: boolean
  variant?: 'success' | 'danger' | 'warning' | 'info'
  className?: string
}

export function StatCardHorizontal({
  label,
  value,
  trend,
  trendValue,
  icon,
  showIcon = true,
  variant,
  className = '',
}: StatCardHorizontalProps) {
  const autoVariant = variant || (trend === 'up' ? 'success' : trend === 'down' ? 'danger' : 'info')
  
  const variantColors = {
    success: 'bg-green-100 text-green-600 dark:bg-green-700 dark:text-green-50',
    danger: 'bg-red-100 text-red-600 dark:bg-red-700 dark:text-red-50',
    warning: 'bg-yellow-100 text-yellow-600 dark:bg-yellow-700 dark:text-yellow-50',
    info: 'bg-blue-100 text-blue-600 dark:bg-blue-700 dark:text-blue-50',
  }

  const TrendIcon = trend === 'up' ? TrendUpIcon : TrendDownIcon

  return (
    <article
      className={`flex items-end justify-between rounded-lg border border-gray-100 bg-white p-6 shadow-xs dark:border-gray-800 dark:bg-gray-900 ${className}`}
    >
      <div className="flex items-center gap-4">
        {showIcon && (
          <span className="hidden rounded-full bg-gray-100 p-2 text-gray-600 dark:bg-gray-800 dark:text-gray-400 sm:block">
            {icon || <DefaultIcon className="size-6" />}
          </span>
        )}

        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{label}</p>
          <p className="text-2xl font-medium text-gray-900 dark:text-white">{value}</p>
        </div>
      </div>

      {(trend || trendValue) && (
        <div className={`inline-flex gap-2 rounded-xs p-1 ${variantColors[autoVariant]}`}>
          {trend && <TrendIcon className="size-4" />}
          {trendValue && <span className="text-xs font-medium">{trendValue}</span>}
        </div>
      )}
    </article>
  )
}

// Iconos
function TrendUpIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
    </svg>
  )
}

function TrendDownIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6" />
    </svg>
  )
}

function DefaultIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth="2"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"
      />
    </svg>
  )
}
