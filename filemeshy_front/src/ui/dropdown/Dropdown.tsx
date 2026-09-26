import { useState, useRef, useEffect, useCallback, useLayoutEffect, type ReactNode, type RefObject, type CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import { ChevronDown } from 'lucide-react'
import { computeMenuCoords, type MenuCoords } from './menuCoords'

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

// Estilo inline del menú portaleado a partir de las coordenadas calculadas.
function menuStyle(coords: MenuCoords): CSSProperties {
  return {
    position: 'fixed',
    top: coords.top,
    bottom: coords.bottom,
    left: coords.left,
    maxHeight: coords.maxHeight,
  }
}

// Hook compartido: mientras el dropdown está abierto, mantiene la posición
// del menú portaleado sincronizada con el trigger real -- recalcula en
// scroll (capture:true para escuchar también el scroll de contenedores
// internos como el overflow-x-auto de DataTable, que no burbujea) y en
// resize de ventana.
function useMenuCoords(
  triggerRef: RefObject<HTMLElement | null>,
  isOpen: boolean,
  position: 'left' | 'right'
) {
  const [coords, setCoords] = useState<MenuCoords | null>(null)

  const updateCoords = useCallback(() => {
    if (!triggerRef.current) return
    setCoords(computeMenuCoords(triggerRef.current, position))
  }, [triggerRef, position])

  useLayoutEffect(() => {
    // Al cerrar no hace falta limpiar coords: el portal ya no se renderiza
    // (gateado por `isOpen &&` del lado del caller), y la próxima apertura
    // recalcula la posición acá mismo antes de pintar.
    if (!isOpen) return
    updateCoords()
    window.addEventListener('resize', updateCoords)
    // capture:true: el scroll de un contenedor interno (ej. overflow-x-auto
    // de DataTable) no burbujea como evento, pero sí se puede capturar.
    document.addEventListener('scroll', updateCoords, true)
    return () => {
      window.removeEventListener('resize', updateCoords)
      document.removeEventListener('scroll', updateCoords, true)
    }
  }, [isOpen, updateCoords])

  return coords
}

export function Dropdown({ trigger, items, position = 'right', className = '' }: DropdownProps) {
  const [isOpen, setIsOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const coords = useMenuCoords(triggerRef, isOpen, position)

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node
      // El menú vive en un portal fuera de este árbol del DOM, así que un
      // click adentro no lo detecta el contains() del trigger -- hay que
      // chequear ambos refs por separado.
      const clickedTrigger = triggerRef.current?.contains(target)
      const clickedMenu = menuRef.current?.contains(target)
      if (!clickedTrigger && !clickedMenu) {
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

  return (
    <div className={`relative inline-flex ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="inline-flex items-center"
        aria-haspopup="true"
        aria-expanded={isOpen}
      >
        {trigger}
      </button>

      {isOpen && coords && createPortal(
        <div
          ref={menuRef}
          role="menu"
          style={menuStyle(coords)}
          className="z-50 w-56 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800"
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
        </div>,
        document.body
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
  const groupRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const coords = useMenuCoords(groupRef, isOpen, position)

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node
      const clickedGroup = groupRef.current?.contains(target)
      const clickedMenu = menuRef.current?.contains(target)
      if (!clickedGroup && !clickedMenu) {
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

  return (
    <div ref={groupRef} className="relative inline-flex">
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

      {isOpen && coords && createPortal(
        <div
          ref={menuRef}
          role="menu"
          style={menuStyle(coords)}
          className="z-50 w-56 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800"
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
        </div>,
        document.body
      )}
    </div>
  )
}
