/**
 * Store de sesión del panel de plataforma (administración de tenants).
 *
 * Persistido en sessionStorage -- NO localStorage, a propósito: la
 * `X-Platform-Key` es un secreto de alto privilegio (permite crear/listar
 * TODOS los tenants), así que la sesión del panel operador debe morir al
 * cerrar la pestaña en vez de sobrevivir indefinidamente en el disco del
 * navegador. Mismo criterio de "vida corta" que ya aplica el resto de la
 * app a los tokens de sesión reales (ver authStore.ts).
 *
 * NO usa el middleware `persist` de zustand: ese envuelve el valor en JSON
 * (`{"state": {...}, "version": 0}`), pero `platformAdmin.api.ts` necesita
 * leer la key como STRING CRUDO desde `sessionStorage.getItem(KEY)` en su
 * interceptor (código plano, fuera de React, sin acoplarse a zustand) --
 * por eso acá se persiste "a mano" con el mismo formato simple que ese
 * interceptor espera. La clave usada en sessionStorage
 * (`filemeshy_platform_key`) es la MISMA que lee `platformAdmin.api.ts`.
 */
import { create } from 'zustand'
import { PLATFORM_KEY_STORAGE_KEY } from '../services/platformAdmin.api'

function readPersistedKey(): string | null {
  try {
    return sessionStorage.getItem(PLATFORM_KEY_STORAGE_KEY)
  } catch {
    // sessionStorage no disponible (ej. modo privado con storage bloqueado)
    return null
  }
}

interface PlatformAuthState {
  key: string | null
  setKey: (key: string) => void
  clearKey: () => void
}

export const usePlatformAuthStore = create<PlatformAuthState>((set) => ({
  key: readPersistedKey(),
  setKey: (key) => {
    try {
      sessionStorage.setItem(PLATFORM_KEY_STORAGE_KEY, key)
    } catch {
      // Ignorar -- si sessionStorage no está disponible, la key igual queda
      // en memoria para esta misma pestaña/render.
    }
    set({ key })
  },
  clearKey: () => {
    try {
      sessionStorage.removeItem(PLATFORM_KEY_STORAGE_KEY)
    } catch {
      // Ignorar, mismo caso de arriba.
    }
    set({ key: null })
  },
}))
