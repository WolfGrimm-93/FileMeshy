import { LogIn, Shield, ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import { useEffect, useRef } from "react";
import { useCompanyInfo } from "@/shared/hooks/useCompanyInfo";
import { useLoginForm } from "@/modules/auth/hooks/useLoginForm";

// Tipo para la API global de Turnstile que inyecta el script de Cloudflare
declare global {
  interface Window {
    turnstile?: {
      render: (container: HTMLElement, options: Record<string, unknown>) => string
      remove: (widgetId: string) => void
      reset: (widgetId: string) => void
    }
  }
}
import { Button } from "@/ui/buttons/Button";
import { Card, CardContent, CardFooter, CardHeader } from "@/ui/cards/Card";
import { EmailInput, PasswordInput, Input } from "@/ui/inputs/Input";
import { env } from "@/shared/config/env";
import fileMeshyLogo from "@/assets/images/logo-filemeshy-color.png";

// Overrides de marca aplicados a componentes compartidos (Button/Input) vía
// className -- esos componentes viven fuera del alcance de este rediseño,
// así que se pisan sus utilidades naranja con `!important` en vez de tocar
// sus archivos fuente.
const BRAND_FOCUS_RING = "focus:border-[#3A64D9]! dark:focus:border-[#6552E0]! focus:ring-0!"
const BRAND_BUTTON = "bg-[#3A64D9]! hover:bg-[#254EC1]! focus:ring-[#3A64D9]! dark:bg-[#3A64D9]! dark:hover:bg-[#254EC1]!"
const BRAND_LINK = "text-[#3A64D9] transition-colors hover:text-[#254EC1] dark:text-[#7C93E8] dark:hover:text-[#9AACEF]"
const BRAND_CARD =
  "w-full max-w-md border-slate-200/80 dark:bg-[#0F1B3D]! dark:border-[#1E2A52]! shadow-[0_20px_60px_-15px_rgba(58,100,217,0.25)] dark:shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]"

/** Barra de acento superior con el gradiente de marca (navy -> azul -> violeta -> cian) */
function BrandAccentBar() {
  return (
    <div
      className="absolute inset-x-0 top-0 h-1 rounded-t-2xl"
      style={{ backgroundImage: "linear-gradient(90deg, #0B1638, #3A64D9, #6552E0, #22D3EE)" }}
      aria-hidden="true"
    />
  )
}

export function LoginForm() {
  const companyInfo = useCompanyInfo();

  const {
    formData,
    isLoading,
    fieldErrors,
    rememberMe,
    setRememberMe,
    emailInputRef,
    passwordInputRef,
    handleChange,
    handleBlur,
    handleSubmit,
    // 2FA
    loginStep,
    totpCode,
    setTotpCode,
    totpInputRef,
    handleTotpSubmit,
    cancelTotp,
    // Turnstile
    turnstileConfig,
    setTurnstileToken,
  } = useLoginForm();

  const turnstileContainerRef = useRef<HTMLDivElement>(null)
  const widgetIdRef = useRef<string | null>(null)
  const showTurnstile = turnstileConfig?.enabled && !!turnstileConfig.site_key

  // Cargar script de Turnstile y renderizar el widget cuando esté listo
  useEffect(() => {
    if (!showTurnstile || !turnstileContainerRef.current) return

    const renderWidget = () => {
      if (!turnstileContainerRef.current || !window.turnstile) return
      // Limpiar widget anterior si existe
      if (widgetIdRef.current) {
        window.turnstile.remove(widgetIdRef.current)
        widgetIdRef.current = null
      }
      widgetIdRef.current = window.turnstile.render(turnstileContainerRef.current, {
        sitekey: turnstileConfig!.site_key,
        callback: (token: unknown) => setTurnstileToken(token as string),
        'expired-callback': () => setTurnstileToken(null),
        'error-callback': () => setTurnstileToken(null),
        theme: 'auto',
        language: 'es',
      })
    }

    if (window.turnstile) {
      renderWidget()
    } else {
      // Cargar script solo si no está ya en el DOM
      if (!document.querySelector('script[data-turnstile]')) {
        const script = document.createElement('script')
        script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js'
        script.async = true
        script.dataset.turnstile = 'true'
        script.onload = renderWidget
        document.head.appendChild(script)
      } else {
        // Script ya en DOM pero aún cargando — esperar
        const interval = setInterval(() => {
          if (window.turnstile) {
            clearInterval(interval)
            renderWidget()
          }
        }, 100)
        return () => clearInterval(interval)
      }
    }

    return () => {
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current)
        widgetIdRef.current = null
      }
    }
  }, [showTurnstile, turnstileConfig?.site_key, setTurnstileToken])

  // ===== PASO 2: Verificación TOTP =====
  if (loginStep === 'totp') {
    return (
      <Card variant="elevated" padding="xl" shadow="2xl" rounded="2xl" className={`relative overflow-hidden ${BRAND_CARD}`}>
        <BrandAccentBar />
        <CardHeader className="space-y-6 pb-8">
          <div className="flex items-center justify-between">
            <button
              onClick={cancelTotp}
              className="flex h-10 w-10 items-center justify-center rounded-lg hover:bg-muted transition-colors"
              title="Volver al inicio de sesión"
            >
              <ArrowLeft className="h-5 w-5 text-muted-foreground" />
            </button>
            <div
              className="flex h-12 w-12 items-center justify-center rounded-2xl shadow-lg"
              style={{ backgroundImage: "linear-gradient(135deg, #3A64D9, #6552E0)" }}
            >
              <Shield className="h-6 w-6 text-white" />
            </div>
            <div className="w-10" />
          </div>
          <div className="space-y-2 text-center">
            <h1 className="heading-font text-2xl font-bold tracking-tight text-foreground">
              Verificación en dos pasos
            </h1>
            <p className="text-sm text-muted-foreground">
              Ingresa el código de 6 dígitos de tu app autenticadora
            </p>
          </div>
        </CardHeader>

        <CardContent className="px-8 pb-8">
          <form onSubmit={handleTotpSubmit} className="space-y-6">
            <Input
              ref={totpInputRef}
              type="text"
              placeholder="000000"
              value={totpCode}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                const val = e.target.value.replace(/\D/g, '').slice(0, 6)
                setTotpCode(val)
              }}
              maxLength={6}
              variant="outlined"
              className={`text-center text-2xl tracking-widest font-mono ${BRAND_FOCUS_RING}`}
              autoComplete="one-time-code"
              inputMode="numeric"
            />

            <div className="rounded-lg bg-[#3A64D9]/6 dark:bg-[#3A64D9]/12 p-4 border border-[#3A64D9]/20 dark:border-[#3A64D9]/25">
              <p className="text-xs text-[#254EC1] dark:text-[#9AACEF]">
                También puedes ingresar un código de respaldo si no tienes acceso a tu app.
              </p>
            </div>

            <Button
              type="submit"
              disabled={isLoading || totpCode.length < 6}
              variant="primary"
              size="lg"
              buttonStyle="solid"
              fullWidth
              isLoading={isLoading}
              loadingText="Verificando..."
              leftIcon={!isLoading ? <Shield className="size-5" /> : undefined}
              shadow="md"
              className={BRAND_BUTTON}
            >
              Verificar
            </Button>
          </form>
        </CardContent>
      </Card>
    )
  }

  // ===== PASO 1: Credenciales =====
  return (
    <>
      <Card
        variant="elevated"
        padding="xl"
        shadow="2xl"
        rounded="2xl"
        className={`relative overflow-hidden ${BRAND_CARD}`}
      >
        <BrandAccentBar />
        <CardHeader className="space-y-6 pb-8">
          {/* Logo */}
          <div className="flex flex-col items-center gap-2">
            {companyInfo?.logo_path ? (
              <img
                src={companyInfo.logo_path}
                alt={companyInfo.business_name}
                className="max-h-24 w-auto max-w-[80%] object-contain"
              />
            ) : (
              <>
                <img
                  src={fileMeshyLogo}
                  alt="FileMeshy"
                  className="max-h-20 w-auto max-w-[80%] object-contain"
                />
                <span className="heading-font text-lg font-semibold tracking-tight text-[#0B1638] dark:text-white">
                  FileMeshy
                </span>
              </>
            )}
          </div>

          {/* Título */}
          <div className="space-y-1.5 text-center">
            <h1 className="heading-font text-2xl font-bold tracking-tight text-foreground">
              Iniciar sesión
            </h1>
            <p className="text-sm text-muted-foreground">
              Accedé a tu mesh de archivos.
            </p>
          </div>
        </CardHeader>

        <CardContent className="px-8 pb-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Campo Empresa (tenant) — solo en builds con selector de tenant habilitado (lab multi-tenant) */}
            {env.tenantSelectorEnabled && (
              <div>
                <label
                  htmlFor="tenantSlug"
                  className="block text-sm font-medium text-foreground/80 mb-2"
                >
                  Empresa
                </label>
                <Input
                  id="tenantSlug"
                  name="tenantSlug"
                  type="text"
                  placeholder="ej: ferreteria-esperanza"
                  value={formData.tenantSlug}
                  onChange={handleChange}
                  onBlur={() => handleBlur("tenantSlug")}
                  variant="outlined"
                  fullWidth
                  className={BRAND_FOCUS_RING}
                />
              </div>
            )}

            {/* Campo Email */}
            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-foreground/80 mb-2"
              >
                Correo electrónico
              </label>
              <EmailInput
                ref={emailInputRef}
                id="email"
                name="email"
                placeholder="tu@email.com"
                value={formData.email}
                onChange={handleChange}
                onBlur={() => handleBlur("email")}
                variant="outlined"
                error={fieldErrors.email}
                fullWidth
                className={BRAND_FOCUS_RING}
              />
            </div>

            {/* Campo Contraseña */}
            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-foreground/80 mb-2"
              >
                Contraseña
              </label>
              <PasswordInput
                ref={passwordInputRef}
                id="password"
                name="password"
                placeholder="••••••••"
                value={formData.password}
                onChange={handleChange}
                onBlur={() => handleBlur("password")}
                variant="outlined"
                error={fieldErrors.password}
                fullWidth
                className={BRAND_FOCUS_RING}
              />
            </div>

            {/* Recuérdame + Olvidaste contraseña */}
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="h-4 w-4 rounded-sm border-gray-300 text-[#3A64D9] accent-[#3A64D9] focus:ring-2 focus:ring-[#3A64D9]"
                />
                <span className="text-sm text-muted-foreground">Recuérdame</span>
              </label>
              <Link
                to="/reset-password"
                className={`text-sm font-medium ${BRAND_LINK}`}
              >
                ¿Olvidaste tu contraseña?
              </Link>
            </div>

            {/* Widget Cloudflare Turnstile — solo en dominio público y si está habilitado */}
            {showTurnstile && (
              <div className="flex justify-center">
                <div ref={turnstileContainerRef} />
              </div>
            )}

            {/* Botón Submit */}
            <Button
              type="submit"
              variant="primary"
              size="lg"
              buttonStyle="solid"
              fullWidth
              isLoading={isLoading}
              loadingText="Iniciando sesión..."
              leftIcon={!isLoading ? <LogIn className="size-5" /> : undefined}
              shadow="md"
              className={BRAND_BUTTON}
            >
              Iniciar sesión
            </Button>
          </form>
        </CardContent>

        <CardFooter className="flex flex-col gap-4 border-t border-gray-200 px-8 pt-6 dark:border-gray-700">
          {/* Links legales */}
          <div className="flex justify-center gap-4 text-xs text-muted-foreground">
            <a href="/about" className="transition-colors hover:text-gray-700 dark:hover:text-gray-300">
              Sobre Nosotros
            </a>
            <span>•</span>
            <a href="/terms" className="transition-colors hover:text-gray-700 dark:hover:text-gray-300">
              Términos
            </a>
            <span>•</span>
            <a href="/privacy" className="transition-colors hover:text-gray-700 dark:hover:text-gray-300">
              Privacidad
            </a>
          </div>
        </CardFooter>
      </Card>
    </>
  );
}
