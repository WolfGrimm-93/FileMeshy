import React from 'react'
import { TrendingUp, TrendingDown } from 'lucide-react'

export type StatTrend = 'up' | 'down'
export type StatVariant = 'success' | 'danger' | 'warning' | 'info'

export interface StatCardProps {
  label: string
  value: string | number
  previousValue?: string | number
  trend?: StatTrend
  trendValue?: string
  variant?: StatVariant
  icon?: React.ReactNode
  className?: string
}

const variantColors = {
  success: {
    bg: 'bg-green-100 dark:bg-green-700',
    text: 'text-green-600 dark:text-green-50',
  },
  danger: {
    bg: 'bg-red-100 dark:bg-red-700',
    text: 'text-red-600 dark:text-red-50',
  },
  warning: {
    bg: 'bg-yellow-100 dark:bg-yellow-700',
    text: 'text-yellow-600 dark:text-yellow-50',
  },
  info: {
    bg: 'bg-blue-100 dark:bg-blue-700',
    text: 'text-blue-600 dark:text-blue-50',
  },
}

export function StatCard({
  label,
  value,
  previousValue,
  trend,
  trendValue,
  variant,
  icon,
  className = '',
}: StatCardProps) {
  const autoVariant = variant || (trend === 'up' ? 'success' : trend === 'down' ? 'danger' : 'info')
  const colors = variantColors[autoVariant]

  const TrendIcon = trend === 'up' ? TrendingUp : TrendingDown

  return (
    <article
      className={`flex flex-col gap-4 rounded-lg border border-gray-100 bg-white p-6 shadow-xs dark:border-gray-800 dark:bg-gray-900 ${className}`}
    >
      {(trend || trendValue || icon) && (
        <div className={`inline-flex gap-2 self-end rounded-xs p-1 ${colors.bg} ${colors.text}`}>
          {icon || (trend && <TrendIcon className="size-4" />)}
          {trendValue && <span className="text-xs font-medium">{trendValue}</span>}
        </div>
      )}

      <div>
        <strong className="block text-sm font-medium text-gray-500 dark:text-gray-400">
          {label}
        </strong>

        <p>
          <span className="text-2xl font-medium text-gray-900 dark:text-white">{value}</span>

          {previousValue && (
            <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">
              desde {previousValue}
            </span>
          )}
        </p>
      </div>
    </article>
  )
}
