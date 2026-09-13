import { useState, type ReactNode } from 'react'

export interface Tab {
  id: string
  label: string
  content: ReactNode
  icon?: ReactNode
  disabled?: boolean
}

export interface TabsProps {
  tabs: Tab[]
  defaultTab?: string
  onChange?: (tabId: string) => void
  variant?: 'underline' | 'pills' | 'enclosed'
  className?: string
}

export function Tabs({
  tabs,
  defaultTab,
  onChange,
  variant = 'underline',
  className = '',
}: TabsProps) {
  const [activeTab, setActiveTab] = useState(defaultTab || tabs[0]?.id)

  const handleTabChange = (tabId: string) => {
    setActiveTab(tabId)
    onChange?.(tabId)
  }

  const activeTabContent = tabs.find((tab) => tab.id === activeTab)?.content

  if (variant === 'underline') {
    return (
      <div className={className}>
        <div className="border-b border-gray-200 dark:border-gray-700">
          <div role="tablist" className="-mb-px flex gap-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                role="tab"
                aria-selected={activeTab === tab.id}
                onClick={() => !tab.disabled && handleTabChange(tab.id)}
                disabled={tab.disabled}
                className={`flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
                  activeTab === tab.id
                    ? 'border-brand-600 text-brand-600 dark:border-brand-500 dark:text-brand-500'
                    : 'border-transparent text-gray-600 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
                } ${tab.disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
              >
                {tab.icon && <span className="size-4">{tab.icon}</span>}
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div role="tabpanel" className="mt-4">
          {activeTabContent}
        </div>
      </div>
    )
  }

  if (variant === 'pills') {
    return (
      <div className={className}>
        <div role="tablist" className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              onClick={() => !tab.disabled && handleTabChange(tab.id)}
              disabled={tab.disabled}
              className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-brand-600 text-white dark:bg-brand-500'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'
              } ${tab.disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
            >
              {tab.icon && <span className="size-4">{tab.icon}</span>}
              {tab.label}
            </button>
          ))}
        </div>

        <div role="tabpanel" className="mt-4">
          {activeTabContent}
        </div>
      </div>
    )
  }

  // Enclosed variant
  return (
    <div className={className}>
      <div className="border-b border-gray-200 dark:border-gray-700">
        <div role="tablist" className="-mb-px flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              onClick={() => !tab.disabled && handleTabChange(tab.id)}
              disabled={tab.disabled}
              className={`flex items-center gap-2 rounded-t-lg border-x border-t px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'border-gray-200 bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-white'
                  : 'border-transparent text-gray-600 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              } ${tab.disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
            >
              {tab.icon && <span className="size-4">{tab.icon}</span>}
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div role="tabpanel" className="rounded-b-lg border border-t-0 border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
        {activeTabContent}
      </div>
    </div>
  )
}
