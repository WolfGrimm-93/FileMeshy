/**
 * User Store
 * Zustand store para gestión de usuarios
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { userService } from '../services/user.service'
import type {
  User,
  UserCreate,
  UserUpdate,
  UserFilters,
  UserStats,
} from '../services/user.service'

interface UserStore {
  // Estado
  users: User[]
  currentUser: User | null
  total: number
  page: number
  pageSize: number
  totalPages: number
  filters: UserFilters
  isLoading: boolean
  error: string | null
  globalStats: UserStats
  lastFetch: number | null

  // Acciones
  fetchUsers: (force?: boolean) => Promise<void>
  fetchStats: () => Promise<void>
  fetchUser: (id: string) => Promise<User | null>
  createUser: (data: UserCreate) => Promise<User | null>
  updateUser: (id: string, data: UserUpdate) => Promise<User | null>
  deleteUser: (id: string) => Promise<boolean>
  setFilters: (filters: UserFilters) => void
  setPage: (page: number) => void
  setPageSize: (pageSize: number) => void
  clearError: () => void
  reset: () => void
}

const CACHE_TIME = 30000 // 30 segundos

export const useUserStore = create<UserStore>()(
  persist(
    (set, get) => ({
      // Estado inicial
      users: [],
      currentUser: null,
      total: 0,
      page: 1,
      pageSize: 50,
      totalPages: 0,
      filters: {},
      isLoading: false,
      error: null,
      globalStats: {
        total: 0,
        total_active: 0,
        total_inactive: 0,
        roles: {},
      },
      lastFetch: null,

      // Obtener estadísticas globales (endpoint /stats separado, con Redis cache)
      fetchStats: async () => {
        try {
          const stats = await userService.getStats()
          set({ globalStats: stats })
        } catch (error) {
          console.error('Error al cargar estadísticas de usuarios:', error)
        }
      },

      // Obtener lista de usuarios con caché inteligente
      fetchUsers: async (force = false) => {
        const { lastFetch, isLoading, users } = get()

        if (isLoading) {
          return
        }

        const hasData = users.length > 0
        const isCacheValid = lastFetch && Date.now() - lastFetch < CACHE_TIME

        if (!force && isCacheValid && hasData) {
          return
        }

        set({ isLoading: true, error: null })

        try {
          const { page, pageSize, filters } = get()
          const skip = (page - 1) * pageSize

          const response = await userService.getUsers({
            ...filters,
            skip,
            limit: pageSize,
          })

          set({
            users: response.items,
            total: response.total,
            totalPages: response.total_pages,
            lastFetch: Date.now(),
            isLoading: false,
          })
        } catch (error: unknown) {
          const errorMessage = error instanceof Error && 'response' in error
            ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : 'Error al cargar usuarios'
          set({
            error: errorMessage || 'Error al cargar usuarios',
            isLoading: false,
          })
          throw error
        }
      },

      // Obtener un usuario específico
      fetchUser: async (id) => {
        set({ isLoading: true, error: null })

        try {
          const user = await userService.getUser(id)
          set({ currentUser: user, isLoading: false })
          return user
        } catch (error: unknown) {
          const errorMessage = error instanceof Error && 'response' in error
            ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : 'Error al cargar usuario'
          set({
            error: errorMessage || 'Error al cargar usuario',
            isLoading: false,
          })
          throw error
        }
      },

      // Crear nuevo usuario
      createUser: async (data) => {
        set({ isLoading: true, error: null })

        try {
          const newUser = await userService.createUser(data)
          await get().fetchUsers(true)
          set({ isLoading: false })
          return newUser
        } catch (error: unknown) {
          const errorMessage = error instanceof Error && 'response' in error
            ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : 'Error al crear usuario'
          set({
            error: errorMessage || 'Error al crear usuario',
            isLoading: false,
          })
          throw error
        }
      },

      // Actualizar usuario
      updateUser: async (id, data) => {
        set({ isLoading: true, error: null })

        try {
          const updatedUser = await userService.updateUser(id, data)

          set((state) => ({
            users: state.users.map((u) =>
              u.id === id ? updatedUser : u
            ),
            currentUser: state.currentUser?.id === id ? updatedUser : state.currentUser,
            isLoading: false,
          }))

          return updatedUser
        } catch (error: unknown) {
          const errorMessage = error instanceof Error && 'response' in error
            ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : 'Error al actualizar usuario'
          set({
            error: errorMessage || 'Error al actualizar usuario',
            isLoading: false,
          })
          throw error
        }
      },

      // Eliminar usuario
      deleteUser: async (id) => {
        set({ isLoading: true, error: null })

        try {
          const state = get()

          await userService.deleteUser(id)

          // Actualización optimista: remover de la lista local
          const newUsers = state.users.filter((u) => u.id !== id)
          const newTotal = state.total - 1

          // Si la página actual queda vacía y no es la primera, retroceder
          const shouldGoBack = newUsers.length === 0 && state.page > 1

          set({
            users: newUsers,
            total: newTotal,
            page: shouldGoBack ? state.page - 1 : state.page,
            isLoading: false,
          })

          // Si retrocedimos de página, recargar
          if (shouldGoBack) {
            await get().fetchUsers(true)
          }

          return true
        } catch (error: unknown) {
          const errorMessage = error instanceof Error && 'response' in error
            ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : 'Error al eliminar usuario'
          set({
            error: errorMessage || 'Error al eliminar usuario',
            isLoading: false,
          })
          throw error
        }
      },

      // Establecer filtros - SOLO actualiza estado (componente controla el fetch)
      setFilters: (filters) => {
        set({ filters, page: 1 })
      },

      // Cambiar página - SOLO actualiza estado
      setPage: (page) => {
        set({ page })
      },

      // Cambiar tamaño de página
      // Validación: No permitir más de 100 (límite backend de usuarios)
      setPageSize: (pageSize) => {
        const validSize = Math.min(pageSize, 100)
        if (pageSize > 100) {
          console.warn(`pageSize ${pageSize} excede límite backend (100). Usando 100.`)
        }
        set({ pageSize: validSize, page: 1 })
      },

      // Limpiar error
      clearError: () => set({ error: null }),

      // Reset completo
      reset: () => set({
        users: [],
        currentUser: null,
        total: 0,
        page: 1,
        pageSize: 50,
        totalPages: 0,
        filters: {},
        isLoading: false,
        error: null,
        globalStats: {
          total: 0,
          total_active: 0,
          total_inactive: 0,
          roles: {},
        },
        lastFetch: null,
      }),
    }),
    {
      name: 'filemeshy_user-preferences',
      partialize: (state) => ({
        page: state.page,
        pageSize: state.pageSize,
        filters: state.filters,
      }),
      // Validar valores al rehidratar desde localStorage
      onRehydrateStorage: () => (state) => {
        if (state && state.pageSize > 100) {
          console.warn(`Corrigiendo pageSize inválido ${state.pageSize} → 100`)
          state.pageSize = 100
        }
      },
    }
  )
)
