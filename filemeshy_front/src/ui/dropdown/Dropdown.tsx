import { useState, useRef, useEffect, type ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'

export interface DropdownItem {
  label?: string
  onClick?: () => void
  href?: string
  icon?: ReactNode
  danger?: boolean
  divider?: boolean
  disabled?: boolean
}

export interface DropdownProps {
  trigger: ReactNode
  items: DropdownItem[]
  position?: 'left' | 'right'
  className?: string
}

export function Dropdown({ trigger, items, position = 'right', className = '' }: DropdownProps) {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      document.addEventListener('keydown', handleEscape)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [isOpen])

  const handleItemClick = (item: DropdownItem) => {
    if (!item.disabled && item.onClick) {
      item.onClick()
    }
    setIsOpen(false)
  }

  const positionClasses = position === 'left' ? 'left-0' : 'right-0'

  return (
    <div ref={dropdownRef} className={`relative inline-flex ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="inline-flex items-center"
        aria-haspopup="true"
        aria-expanded={isOpen}
      >
        {trigger}
      </button>

      {isOpen && (
        <div
          role="menu"
          className={`absolute top-full z-50 mt-2 w-56 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800 ${positionClasses}`}
        >
          {items.map((item, index) => {
            if (item.divider) {
              return (
                <div
                  key={`divider-${index}`}
                  className="my-1 h-px bg-gray-200 dark:bg-gray-700"
                />
              )
            }

            const itemClasses = `flex w-full items-center gap-2 px-4 py-2 text-sm font-medium transition-colors ${
              item.danger
                ? 'text-red-700 hover:bg-red-50 dark:text-red-500 dark:hover:bg-red-900/20'
                : 'text-gray-700 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-700 dark:hover:text-white'
            } ${item.disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`

            if (item.href && !item.disabled) {
              return (
                <a
                  key={index}
                  href={item.href}
                  className={itemClasses}
                  role="menuitem"
                  onClick={() => setIsOpen(false)}
                >
                  {item.icon && <span className="size-4">{item.icon}</span>}
                  {item.label}
                </a>
              )
            }

            return (
              <button
                key={index}
                type="button"
                className={itemClasses}
                role="menuitem"
                onClick={() => handleItemClick(item)}
                disabled={item.disabled}
              >
                {item.icon && <span className="size-4">{item.icon}</span>}
                {item.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

// Split Button Dropdown
export interface SplitButtonProps {
  label: string
  onClick: () => void
  items: DropdownItem[]
  variant?: 'primary' | 'secondary' | 'success' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  position?: 'left' | 'right'
}

export function SplitButton({
  label,
  onClick,
  items,
  variant = 'primary',
  size = 'md',
  position = 'right',
}: SplitButtonProps) {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  const variantClasses = {
    primary: 'bg-brand-600 text-white hover:bg-brand-700 dark:bg-brand-500 dark:hover:bg-brand-600',
    secondary: 'bg-gray-200 text-gray-900 hover:bg-gray-300 dark:bg-gray-700 dark:text-white dark:hover:bg-gray-600',
    success: 'bg-green-600 text-white hover:bg-green-700 dark:bg-green-500 dark:hover:bg-green-600',
    danger: 'bg-red-600 text-white hover:bg-red-700 dark:bg-red-500 dark:hover:bg-red-600',
  }

  const sizeClasses = {
    sm: 'px-3 py-1.5 text-xs',
    md: 'px-4 py-2 text-sm',
    lg: 'px-5 py-2.5 text-base',
  }

  const baseClasses = variantClasses[variant]
  const sizing = sizeClasses[size]
  const positionClasses = position === 'left' ? 'left-0' : 'right-0'

  return (
    <div ref={dropdownRef} className="relative inline-flex">
      <span className="inline-flex divide-x divide-white/20 overflow-hidden rounded-lg shadow-xs">
        <button
          type="button"
          onClick={onClick}
          className={`${baseClasses} ${sizing} font-medium transition-colors focus:relative`}
        >
          {label}
        </button>

        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className={`${baseClasses} ${sizing} transition-colors focus:relative`}
          aria-label="Menu"
          aria-haspopup="true"
          aria-expanded={isOpen}
        >
          <ChevronDown className="size-4" />
        </button>
      </span>

      {isOpen && (
        <div
          role="menu"
          className={`absolute top-full z-50 mt-2 w-56 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800 ${positionClasses}`}
        >
          {items.map((item, index) => {
            if (item.divider) {
              return (
                <div
                  key={`divider-${index}`}
                  className="my-1 h-px bg-gray-200 dark:bg-gray-700"
                />
              )
            }

            const itemClasses = `flex w-full items-center gap-2 px-4 py-2 text-sm font-medium transition-colors ${
              item.danger
                ? 'text-red-700 hover:bg-red-50 dark:text-red-500 dark:hover:bg-red-900/20'
                : 'text-gray-700 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-700 dark:hover:text-white'
            } ${item.disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`

            return (
              <button
                key={index}
                type="button"
                className={itemClasses}
                role="menuitem"
                onClick={() => {
                  if (!item.disabled && item.onClick) {
                    item.onClick()
                  }
                  setIsOpen(false)
                }}
                disabled={item.disabled}
              >
                {item.icon && <span className="size-4">{item.icon}</span>}
                {item.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
