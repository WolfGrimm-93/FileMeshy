import { createContext } from 'react'

export type Theme = 'light' | 'dark' | 'system'

export type ThemeProviderState = {
  theme: Theme
  setTheme: (theme: Theme) => void
  actualTheme: 'light' | 'dark'
}

const initialState: ThemeProviderState = {
  theme: 'system',
  setTheme: () => null,
  actualTheme: 'light',
}

export const ThemeProviderContext = createContext<ThemeProviderState>(initialState)
