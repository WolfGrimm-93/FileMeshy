import { useState } from 'react'
import { Eye, EyeOff, Shield, Info, Save, Loader2, Clock } from 'lucide-react'
import { useSeguridadConfig } from '../hooks/useSeguridadConfig'

const SUB_TABS = [
  { id: 'captcha'   as const, label: 'CAPTCHA',   icono: Shield },
  { id: 'sesiones'  as const, label: 'Sesiones',  icono: Clock  },
]

function Toggle({ checked, onChange }: { checked: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      onClick={onChange}
      className={`relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors ${checked ? 'bg-brand-600' : 'bg-border'}`}
    >
      <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-xs transition duration-200 mt-0.5 ${checked ? 'translate-x-[18px]' : 'translate-x-0.5'}`} />
    </button>
  )
}

export default function SeguridadPage() {
  const { form, setForm, isLoading, isSaving, isDirty, saveConfig } = useSeguridadConfig()
  const [showSecret, setShowSecret] = useState(false)
  const [activeTab, setActiveTab] = useState<'captcha' | 'sesiones'>('captcha')

  // Sesiones — local, sin backend aún
  const [sessionTimeout, setSessionTimeout] = useState('480')
  const [lockOnInactivity, setLockOnInactivity] = useState(true)

  if (isLoading || !form) {
    return (
      <div className="flex items-center justify-center h-40">
        <Loader2 size={20} className="animate-spin text-brand-600" />
        <span className="ml-2 text-sm text-muted-foreground">Cargando...</span>
      </div>
    )
  }

  const set = <K extends keyof typeof form>(field: K, value: typeof form[K]) =>
    setForm(prev => prev ? { ...prev, [field]: value } : prev)

  return (
    <div className="space-y-4">

      {/* Sub-tab nav */}
      <div className="flex gap-1 p-1 bg-muted rounded-xl border border-border">
        {SUB_TABS.map(tab => {
          const Icon = tab.icono
          const active = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                active
                  ? 'bg-card text-foreground shadow-xs border border-border'
                  : 'text-muted-foreground hover:text-foreground hover:bg-card/50'
              }`}
            >
              <Icon size={14} />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* ── CAPTCHA ── */}
      {activeTab === 'captcha' && (
        <>
          <div className="bg-card rounded-xl border border-border overflow-hidden">
            <div className="px-5 py-3.5 flex items-center gap-2.5 border-b border-border">
              <Shield size={15} className="text-primary" />
              <h3 className="text-sm font-semibold text-foreground">CAPTCHA — Cloudflare Turnstile</h3>
            </div>
            <div className="p-5 space-y-5">
              <div className="flex gap-3 p-3.5 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                <Info size={15} className="text-blue-500 shrink-0 mt-0.5" />
                <p className="text-xs text-blue-700 dark:text-blue-300 leading-relaxed">
                  Cuando está activado, el login en el dominio público muestra un desafío CAPTCHA antes
                  de enviar las credenciales. Los accesos desde red local y la app de escritorio
                  se saltan el CAPTCHA automáticamente.
                </p>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-foreground">Activar Turnstile</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Requiere Site Key y Secret Key configuradas para funcionar
                  </p>
                </div>
                <Toggle checked={form.turnstileEnabled} onChange={() => set('turnstileEnabled', !form.turnstileEnabled)} />
              </div>

              <div className="border-t border-border" />

              <div>
                <label className="block text-sm font-medium text-foreground/80 mb-1.5" htmlFor="seg-page-1">
                  Site Key <span className="text-xs text-muted-foreground">(pública)</span>
                </label>
                <input id="seg-page-1"
                  type="text"
                  value={form.turnstileSiteKey}
                  onChange={e => set('turnstileSiteKey', e.target.value)}
                  placeholder="0x4AAAAAAA..."
                  className="w-full px-3 py-2 text-sm border border-input rounded-lg bg-muted text-foreground font-mono focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                  autoComplete="off"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Se obtiene en el dashboard de Cloudflare → Turnstile → tu widget.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground/80 mb-1.5" htmlFor="seg-page-2">
                  Secret Key <span className="text-xs text-muted-foreground">(privada — solo escritura)</span>
                </label>
                <div className="relative">
                  <input id="seg-page-2"
                    type={showSecret ? 'text' : 'password'}
                    value={form.turnstileSecretKey}
                    onChange={e => set('turnstileSecretKey', e.target.value)}
                    placeholder={form.turnstileSecretKeyConfigured ? '••••••••••••••••••• (ya configurada)' : '0x4AAAAAAA...'}
                    className="w-full px-3 py-2 pr-10 text-sm border border-input rounded-lg bg-muted text-foreground font-mono focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                    autoComplete="new-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowSecret(v => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {showSecret ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {form.turnstileSecretKeyConfigured
                    ? 'Ya hay una secret key guardada. Deja vacío para no cambiarla.'
                    : 'Se almacena cifrada. Nunca se muestra una vez guardada.'}
                </p>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                  form.turnstileEnabled
                    ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                    : 'bg-muted text-muted-foreground'
                }`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${form.turnstileEnabled ? 'bg-green-500' : 'bg-muted-foreground'}`} />
                  {form.turnstileEnabled ? 'Turnstile activo' : 'Turnstile inactivo'}
                </span>
                {form.turnstileEnabled && (!form.turnstileSiteKey || !form.turnstileSecretKeyConfigured) && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400">
                    ⚠ Faltan claves — el CAPTCHA no funcionará
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="flex justify-end">
            <button
              onClick={saveConfig}
              disabled={isSaving || !isDirty}
              className="flex items-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-semibold transition disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isSaving ? <><Loader2 size={14} className="animate-spin" /> Guardando...</> : <><Save size={14} /> Guardar</>}
            </button>
          </div>
        </>
      )}

      {/* ── Sesiones ── */}
      {activeTab === 'sesiones' && (
        <div className="bg-card rounded-xl border border-border overflow-hidden">
          <div className="px-5 py-3.5 flex items-center gap-2.5 border-b border-border">
            <Clock size={15} className="text-primary" />
            <h3 className="text-sm font-semibold text-foreground">Políticas de Sesión</h3>
          </div>
          <div className="p-5 space-y-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-foreground">Bloquear por inactividad</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Cierra la sesión automáticamente tras el tiempo configurado sin actividad
                </p>
              </div>
              <Toggle checked={lockOnInactivity} onChange={() => setLockOnInactivity(v => !v)} />
            </div>

            {lockOnInactivity && (
              <>
                <div className="border-t border-border" />
                <div>
                  <label className="block text-sm font-medium text-foreground/80 mb-1.5" htmlFor="seg-page-3">
                    Tiempo de inactividad
                  </label>
                  <select id="seg-page-3"
                    value={sessionTimeout}
                    onChange={e => setSessionTimeout(e.target.value)}
                    className="w-full sm:w-64 px-3 py-2 text-sm border border-input rounded-lg bg-muted text-foreground focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                  >
                    <option value="15">15 minutos</option>
                    <option value="30">30 minutos</option>
                    <option value="60">1 hora</option>
                    <option value="240">4 horas</option>
                    <option value="480">8 horas</option>
                  </select>
                  <p className="text-xs text-muted-foreground mt-1">
                    La sesión expirará si no hay actividad durante este tiempo
                  </p>
                </div>
              </>
            )}

            <div className="flex gap-2 p-3 bg-muted rounded-lg border border-border">
              <Info size={14} className="text-muted-foreground shrink-0 mt-0.5" />
              <p className="text-xs text-muted-foreground leading-relaxed">
                La configuración de sesiones se aplicará en una próxima actualización del sistema.
              </p>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
