import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

let currentUser: { first_name: string; last_name: string; avatar?: string } = { first_name: 'Ana', last_name: 'P', avatar: 'http://x/media/a.webp' }
vi.mock('@/modules/auth/hooks/useAuth', () => ({ useAuth: () => ({ user: currentUser }) }))
vi.mock('@/app/hooks/useTheme', () => ({ useTheme: () => ({ actualTheme: 'light', setTheme: vi.fn() }) }))
vi.mock('@/app/store/sidebarStore', () => ({ useSidebarStore: () => ({ collapsed: false, toggle: vi.fn() }) }))
vi.mock('@/modules/notifications/store/notificationStore', () => ({
  useNotificationStore: () => ({
    notifications: [], unreadCount: 0, fetchNotifications: vi.fn(), fetchUnreadCount: vi.fn(), markAsRead: vi.fn(),
  }),
}))
vi.mock('@/modules/auth/components/SwitchUserModal', () => ({ default: () => null }))

import Navbar from './Navbar'

const renderNavbar = () => render(<MemoryRouter><Navbar /></MemoryRouter>)
const avatarImg = (c: HTMLElement) => c.querySelector('img[src="http://x/media/a.webp"]')

describe('Navbar avatar', () => {
  it('renderiza el avatar con su URL', () => {
    currentUser = { first_name: 'Ana', last_name: 'P', avatar: 'http://x/media/a.webp' }
    const { container } = renderNavbar()
    expect(avatarImg(container)).not.toBeNull()
  })

  it('si la imagen falla al cargar muestra el icono de fallback, no una imagen rota', () => {
    currentUser = { first_name: 'Ana', last_name: 'P', avatar: 'http://x/media/a.webp' }
    const { container } = renderNavbar()
    fireEvent.error(avatarImg(container)!)
    expect(avatarImg(container)).toBeNull()
    expect(container.querySelector('svg.lucide-user')).not.toBeNull()
  })
})
