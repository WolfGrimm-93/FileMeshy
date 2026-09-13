import { useState, useEffect } from 'react'
import { Bell, Mail, Send, Loader2, Wifi, Save } from 'lucide-react'
import { toast } from '@/ui/toast/CustomToast'
import { adminConfigurationService, DEFAULT_NOTIF_TYPES_CONFIG } from '../services/admin-configuration.service'
import type { NotificationTypesConfig } from '../services/admin-configuration.service'

const ENCRYPTION_OPTIONS = [
  { value: 'tls',     label: 'TLS / STARTTLS (puerto 587)' },
  { value: 'ssl',     label: 'SSL implícito (puerto 465)'  },
  { value: 'ninguno', label: 'Sin cifrado (no recomendado)' },
]

// Los tipos de negocio no relacionado (stock/pagos/ventas/compras/clientes) se
// podaron junto con sus tasks del backend -- ver app/configuration/router.py::_DEFAULT_NOTIF_TYPES_CONFIG.
// Vacío hasta que existan eventos reales del dominio de archivos que notificar.
const TIPOS_NOTIFICACIONES: { id: string; label: string }[] = []

const SUB_TABS = [
  { id: 'correo' as const, label: 'Correo',        icono: Send },
  { id: 'tipos'  as const, label: 'Tipos',         icono: Bell },
]

export default function NotificacionesTab() {
  const [activeTab, setActiveTab] = useState<'correo' | 'tipos'>('correo')

  // ── SMTP local state ───────────────────────────────────────────────────────
  const [smtp, setSmtp] = useState({
    account_email:      '',
    smtp_host:          '',
    smtp_username:      '',
    smtp_password:      '',   // '' = no change; '****' = already set (show placeholder)
    smtp_insecure_port: 587,
    smtp_secure_port:   465,
    encryption:         'tls',
  })
  const [passwordIsSet, setPasswordIsSet]     = useState(false)
  const [loadingSmtp, setLoadingSmtp]         = useState(true)
  const [savingSmtp,  setSavingSmtp]          = useState(false)
  const [testingSmtp, setTestingSmtp]         = useState(false)

  // ── Tipos de notificaciones local state ───────────────────────────────────
  const [notifTypes, setNotifTypes]           = useState<NotificationTypesConfig>(DEFAULT_NOTIF_TYPES_CONFIG)
  const [loadingTypes, setLoadingTypes]       = useState(true)
  const [savingTypes,  setSavingTypes]        = useState(false)

  // Cargar config de email desde la API al montar
  useEffect(() => {
    const load = async () => {
      try {
        const data = await adminConfigurationService.getEmailConfig()
        setSmtp(prev => ({
          ...prev,
          account_email:      data.account_email      || '',
          smtp_host:          data.smtp_host          || '',
          smtp_username:      data.smtp_username      || '',
          smtp_password:      '',   // nunca prefill de contraseña
          smtp_insecure_port: data.smtp_insecure_port || 587,
          smtp_secure_port:   data.smtp_secure_port   || 465,
        }))
        setPasswordIsSet(data.smtp_password === '****')
      } catch {
        // Sin config aún — campos en blanco
      } finally {
        setLoadingSmtp(false)
      }
    }
    load()
  }, [])

  // Cargar tipos de notificaciones desde la API al montar
  useEffect(() => {
    const load = async () => {
      try {
        const data = await adminConfigurationService.getNotificationTypes()
        setNotifTypes(data)
      } catch {
        // Sin config aún — usar defaults
      } finally {
        setLoadingTypes(false)
      }
    }
    load()
  }, [])

  const handleSmtpChange = (field: string, value: string | number) => {
    setSmtp(prev => ({ ...prev, [field]: value }))
  }

  const handleToggleNotifType = (typeId: string, channel: 'email' | 'sistema') => {
    setNotifTypes(prev => ({
      ...prev,
      [typeId]: { ...prev[typeId], [channel]: !prev[typeId]?.[channel] },
    }))
  }

  const handleSaveNotifTypes = async () => {
    setSavingTypes(true)
    try {
      await adminConfigurationService.updateNotificationTypes(notifTypes)
      toast.success('Tipos de notificaciones guardados')
    } catch {
      toast.error('Error al guardar los tipos de notificaciones')
    } finally {
      setSavingTypes(false)
    }
  }

  const handleSaveSmtp = async () => {
    if (!smtp.smtp_host || !smtp.smtp_username || !smtp.account_email) {
      toast.error('Servidor SMTP, usuario y email remitente son obligatorios')
      return
    }

    setSavingSmtp(true)
    try {
      const payload: Record<string, string | number> = {
        email_method:        'smtp',
        account_email:       smtp.account_email,
        smtp_host:           smtp.smtp_host,
        smtp_username:       smtp.smtp_username,
        smtp_insecure_port:  smtp.smtp_insecure_port,
        smtp_secure_port:    smtp.smtp_secure_port,
      }
      if (smtp.smtp_password && smtp.smtp_password !== '****') {
        payload.smtp_password = smtp.smtp_password
      }

      await adminConfigurationService.updateEmailConfig(payload)
      setPasswordIsSet(true)
      setSmtp(prev => ({ ...prev, smtp_password: '' }))
      toast.success('Configuración guardada correctamente')
    } catch {
      toast.error('Error al guardar la configuración')
    } finally {
      setSavingSmtp(false)
    }
  }

  const handleTestSmtp = async () => {
    setTestingSmtp(true)
    try {
      const result = await adminConfigurationService.testSmtpConnection()
      toast.success(result.message || 'Conexión exitosa')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Error al probar la conexión SMTP'
      toast.error(msg)
    } finally {
      setTestingSmtp(false)
    }
  }

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

      {/* ── Correo ── */}
      {activeTab === 'correo' && (
        <div className="bg-card rounded-xl border border-border overflow-hidden">
          <div className="px-5 py-3.5 flex items-center gap-2.5 border-b border-border">
            <Send size={15} className="text-primary" />
            <h3 className="text-sm font-semibold text-foreground">Proveedor de correo electrónico</h3>
          </div>
          <div className="p-5">
            {loadingSmtp ? (
              <div className="flex items-center justify-center py-6 gap-2 text-muted-foreground">
                <Loader2 size={18} className="animate-spin" />
                <span className="text-sm">Cargando configuración...</span>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Email remitente */}
                <div>
                  <label className="block text-sm font-medium text-foreground/80 mb-1">
                    Email remitente <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="email"
                    value={smtp.account_email}
                    onChange={e => handleSmtpChange('account_email', e.target.value)}
                    placeholder="noreply@tudominio.com"
                    className="w-full px-3 py-2.5 border border-input rounded-lg bg-muted text-foreground text-sm focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                  />
                  <p className="mt-1 text-xs text-muted-foreground">Dirección que aparecerá como remitente en todos los correos</p>
                </div>

                {/* Formulario SMTP */}
                <div className="space-y-4 pt-2 border-t border-border">
                  <p className="text-xs font-medium text-muted-foreground pt-1">Servidor SMTP</p>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="md:col-span-2">
                      <label className="block text-sm font-medium text-foreground/80 mb-1">
                        Host SMTP <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="text"
                        value={smtp.smtp_host}
                        onChange={e => handleSmtpChange('smtp_host', e.target.value)}
                        placeholder="mail.tudominio.com"
                        className="w-full px-3 py-2.5 border border-input rounded-lg bg-muted text-foreground text-sm focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-foreground/80 mb-1">Puerto</label>
                      <input
                        type="text"
                        inputMode="numeric"
                        pattern="[0-9]*"
                        value={smtp.smtp_insecure_port}
                        onChange={e => {
                          const raw = e.target.value.replace(/\D/g, '')
                          handleSmtpChange('smtp_insecure_port', raw === '' ? 0 : parseInt(raw, 10))
                        }}
                        className="w-full px-3 py-2.5 border border-input rounded-lg bg-muted text-foreground text-sm focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-foreground/80 mb-1">
                        Usuario SMTP <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="text"
                        value={smtp.smtp_username}
                        onChange={e => handleSmtpChange('smtp_username', e.target.value)}
                        placeholder="correo@tudominio.com"
                        className="w-full px-3 py-2.5 border border-input rounded-lg bg-muted text-foreground text-sm focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-foreground/80 mb-1">
                        Contraseña SMTP
                        {passwordIsSet && (
                          <span className="ml-2 text-xs text-green-600 dark:text-green-400 font-normal">
                            (configurada — deja en blanco para no cambiar)
                          </span>
                        )}
                      </label>
                      <input
                        type="password"
                        value={smtp.smtp_password}
                        onChange={e => handleSmtpChange('smtp_password', e.target.value)}
                        placeholder={passwordIsSet ? '••••••••' : 'Contraseña'}
                        className="w-full px-3 py-2.5 border border-input rounded-lg bg-muted text-foreground text-sm focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                      />
                    </div>
                  </div>

                  <div className="w-full sm:w-64">
                    <label className="block text-sm font-medium text-foreground/80 mb-1">Cifrado</label>
                    <select
                      value={smtp.encryption}
                      onChange={e => {
                        const enc = e.target.value
                        handleSmtpChange('encryption', enc)
                        if (enc === 'tls')     handleSmtpChange('smtp_insecure_port', 587)
                        if (enc === 'ssl')     handleSmtpChange('smtp_insecure_port', 465)
                        if (enc === 'ninguno') handleSmtpChange('smtp_insecure_port', 25)
                      }}
                      className="w-full px-3 py-2.5 border border-input rounded-lg bg-muted text-foreground text-sm focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                    >
                      {ENCRYPTION_OPTIONS.map(o => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Botones */}
                <div className="flex flex-col sm:flex-row gap-3 pt-2">
                  <button
                    onClick={handleSaveSmtp}
                    disabled={savingSmtp}
                    className="flex items-center justify-center gap-2 px-5 py-2.5 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
                  >
                    {savingSmtp ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                    {savingSmtp ? 'Guardando...' : 'Guardar configuración'}
                  </button>
                  <button
                    onClick={handleTestSmtp}
                    disabled={testingSmtp || !smtp.smtp_host}
                    className="flex items-center justify-center gap-2 px-5 py-2.5 border border-input hover:bg-muted disabled:opacity-50 text-foreground/80 text-sm font-medium rounded-lg transition-colors"
                  >
                    {testingSmtp ? <Loader2 size={16} className="animate-spin" /> : <Wifi size={16} />}
                    {testingSmtp ? 'Probando...' : 'Probar conexión'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Tipos de notificaciones ── */}
      {activeTab === 'tipos' && (
        <div className="bg-card rounded-xl border border-border overflow-hidden">
          <div className="px-5 py-3.5 flex items-center gap-2.5 border-b border-border">
            <Bell size={15} className="text-primary" />
            <div>
              <h3 className="text-sm font-semibold text-foreground">Tipos de Notificaciones</h3>
              <p className="text-xs text-muted-foreground mt-0.5">Controla qué eventos generan notificaciones y por qué canal</p>
            </div>
          </div>
          <div className="p-5">
            {loadingTypes ? (
              <div className="flex items-center justify-center py-6 gap-2 text-muted-foreground">
                <Loader2 size={18} className="animate-spin" />
                <span className="text-sm">Cargando...</span>
              </div>
            ) : TIPOS_NOTIFICACIONES.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-center gap-2">
                <Bell size={24} className="text-muted-foreground" />
                <p className="text-sm text-foreground font-medium">Sin tipos de notificación todavía</p>
                <p className="text-xs text-muted-foreground max-w-sm">
                  Se van a poder configurar cuando el sistema tenga eventos reales del dominio de
                  archivos que notificar (ej. archivo compartido, cuota de almacenamiento al límite).
                </p>
              </div>
            ) : (
              <>
                <div className="border border-border rounded-lg overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-border bg-muted">
                          <th className="text-left py-3 px-4 text-sm font-semibold text-foreground">Evento</th>
                          <th className="text-center py-3 px-4 text-sm font-semibold text-foreground w-28">
                            <Mail size={14} className="inline mr-1" />Email
                          </th>
                          <th className="text-center py-3 px-4 text-sm font-semibold text-foreground w-28">
                            <Bell size={14} className="inline mr-1" />Sistema
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {TIPOS_NOTIFICACIONES.map((tipo, idx) => {
                          const emailActivo   = notifTypes[tipo.id]?.email   ?? true
                          const sistemaActivo = notifTypes[tipo.id]?.sistema  ?? true
                          return (
                            <tr key={tipo.id} className={`border-b border-border ${idx % 2 === 0 ? 'bg-card' : 'bg-muted/50'}`}>
                              <td className="py-3 px-4 text-sm font-medium text-foreground">{tipo.label}</td>
                              <td className="text-center py-3 px-4">
                                <button
                                  onClick={() => handleToggleNotifType(tipo.id, 'email')}
                                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${emailActivo ? 'bg-brand-600' : 'bg-border'}`}
                                >
                                  <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${emailActivo ? 'translate-x-4' : 'translate-x-0.5'}`} />
                                </button>
                              </td>
                              <td className="text-center py-3 px-4">
                                <button
                                  onClick={() => handleToggleNotifType(tipo.id, 'sistema')}
                                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${sistemaActivo ? 'bg-brand-600' : 'bg-border'}`}
                                >
                                  <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${sistemaActivo ? 'translate-x-4' : 'translate-x-0.5'}`} />
                                </button>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="mt-4 flex justify-end">
                  <button
                    onClick={handleSaveNotifTypes}
                    disabled={savingTypes}
                    className="flex items-center gap-2 px-5 py-2.5 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
                  >
                    {savingTypes ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                    {savingTypes ? 'Guardando...' : 'Guardar tipos'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

    </div>
  )
}
