/**
 * Root Layout Component para React Router v7
 * Incluye AuthProvider, ConfigProvider y configuración global
 */

import { Outlet } from 'react-router-dom'
import { Suspense, useEffect } from 'react'
import { AuthProvider } from '@/modules/auth/components/AuthProvider'
import { ConfigProvider } from '@/modules/configuration/providers/ConfigProvider'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { FullScreenLoader } from '@/ui/loading'

function SplashRemover({ children }: { children: React.ReactNode }) {
  useEffect(() => { window.__removeSplash?.() }, [])
  return <>{children}</>
}

export function RootLayout() {
  return (
    <ErrorBoundary>
      <ConfigProvider>
        <AuthProvider>
          <Suspense fallback={<FullScreenLoader />}>
            <SplashRemover>
              <Outlet />
            </SplashRemover>
          </Suspense>
        </AuthProvider>
      </ConfigProvider>
    </ErrorBoundary>
  )
}
