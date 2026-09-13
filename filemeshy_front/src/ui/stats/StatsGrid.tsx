import { type ReactNode } from 'react'

type StatVariant = 'default' | 'success' | 'warning' | 'danger' | 'info'

interface StatItem {
  icon: ReactNode
  label: string
  value: string | number
  variant?: StatVariant
  onClick?: () => void
}

interface StatsGridProps {
  stats: StatItem[]
  className?: string
}

const variantStyles: Record<StatVariant, { bg: string; text: string; iconBg: string; iconText: string }> = {
  default: {
    bg: 'bg-gray-100 dark:bg-gray-800',
    text: 'text-gray-900 dark:text-white',
    iconBg: 'bg-gray-100 dark:bg-gray-800',
    iconText: 'text-gray-600 dark:text-gray-400'
  },
  success: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-700 dark:text-green-400',
    iconBg: 'bg-green-100 dark:bg-green-900/30',
    iconText: 'text-green-600 dark:text-green-400'
  },
  warning: {
    bg: 'bg-brand-100 dark:bg-brand-900/30',
    text: 'text-brand-700 dark:text-brand-400',
    iconBg: 'bg-brand-100 dark:bg-brand-900/30',
    iconText: 'text-brand-600 dark:text-brand-400'
  },
  danger: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-700 dark:text-red-400',
    iconBg: 'bg-red-100 dark:bg-red-900/30',
    iconText: 'text-red-600 dark:text-red-400'
  },
  info: {
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    text: 'text-blue-700 dark:text-blue-400',
    iconBg: 'bg-blue-100 dark:bg-blue-900/30',
    iconText: 'text-blue-600 dark:text-blue-400'
  }
}

export function StatsGrid({ stats, className = '' }: StatsGridProps) {
  return (
    <div className={`flex items-center gap-6 divide-x divide-gray-200 dark:divide-gray-700 ${className}`}>
      {stats.map((stat, index) => {
        const variant = stat.variant || 'default'
        const styles = variantStyles[variant]
        
        const inner = (
          <>
            <div className={`p-2 rounded-lg ${styles.iconBg}`}>
              <div className={`w-5 h-5 ${styles.iconText}`}>
                {stat.icon}
              </div>
            </div>
            <div>
              <p className={`text-xs ${variant === 'default' ? 'text-gray-500 dark:text-gray-500' : styles.iconText}`}>
                {stat.label}
              </p>
              <p className={`text-lg font-semibold ${styles.text}`}>
                {stat.value}
              </p>
            </div>
          </>
        )

        return stat.onClick ? (
          <button
            key={index}
            onClick={stat.onClick}
            className={`flex items-center gap-3 ${index > 0 ? 'pl-6' : ''} rounded-lg px-1 hover:opacity-75 transition-opacity cursor-pointer`}
          >
            {inner}
          </button>
        ) : (
          <div key={index} className={`flex items-center gap-3 ${index > 0 ? 'pl-6' : ''}`}>
            {inner}
          </div>
        )
      })}
    </div>
  )
}
