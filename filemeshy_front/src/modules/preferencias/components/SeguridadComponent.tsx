/**
 * COMPONENTE - SEGURIDAD
 * Gestiona cambio de contraseña, 2FA y sesiones activas
 */
import { useState, useEffect, useCallback } from 'react'
import { Shield, Lock, Key, Eye, EyeOff, Laptop, Smartphone, Trash2, AlertTriangle, Loader2, CheckCircle2, Copy, XCircle, LogOut } from 'lucide-react'
import { toast } from '@/ui/toast/CustomToast'
import { authService } from '@/modules/auth/services/auth.service'
import type { PasswordChange, SecurityPolicies, TwoFactorSetupData, TwoFactorStatus } from '@/modules/auth/services/auth.service'
import type { AxiosError } from 'axios'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import { userService } from '@/modules/users/services/user.service'
import type { UserSession } from '@/modules/users/services/user.service'
import { formatDateTime } from '@/shared/utils/dates'
import { ConfirmModal } from '@/ui/modals/Modal'

interface SeguridadProps {
  onSave?: () => void
}

type TwoFAView = 'idle' | 'setup' | 'verify-enable' | 'show-backup' | 'verify-disable'

export default function SeguridadComponent({ onSave }: SeguridadProps) {
  const { user: authUser } = useAuth()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)

  // --- Estado 2FA ---
  const [twoFAStatus, setTwoFAStatus] = useState<TwoFactorStatus | null>(null)
  const [twoFAView, setTwoFAView] = useState<TwoFAView>('idle')
  const [setupData, setSetupData] = useState<TwoFactorSetupData | null>(null)
  const [totpCode, setTotpCode] = useState('')
  const [twoFALoading, setTwoFALoading] = useState(false)
  const [backupCodes, setBackupCodes] = useState<string[]>([])

  // --- Estado modales de sesiones ---
  const [revokeModal, setRevokeModal] = useState<{ open: boolean; sessionId: string | null; deviceName: string }>({
    open: false, sessionId: null, deviceName: ''
  })
  const [revokeAllModal, setRevokeAllModal] = useState(false)
  const [revokingSession, setRevokingSession] = useState(false)
  
  const DEFAULT_POLICIES: SecurityPolicies = {
    min_password_length: 8,
    require_uppercase: true,
    require_lowercase: true,
    require_numbers: true,
    require_special_chars: false,
  } as SecurityPolicies

  const [policies, setPolicies] = useState<SecurityPolicies>(DEFAULT_POLICIES)
  const [sessions, setSessions] = useState<UserSession[]>([])
  
  const [passwordData, setPasswordData] = useState<PasswordChange>({
    current_password: '',
    new_password: '',
    confirm_password: ''
  })

  const [passwordStrength, setPasswordStrength] = useState({
    strength: 0,
    message: ''
  })

  const loadSecurityData = async () => {
    if (!authUser) return
    try {
      setLoading(true)
      const [policiesData, sessionsData, status2fa] = await Promise.allSettled([
        authService.getSecurityPolicies(),
        userService.getUserSessions(authUser.id),
        authService.get2FAStatus(),
      ])
      if (policiesData.status === 'fulfilled') setPolicies(policiesData.value)
      if (sessionsData.status === 'fulfilled') setSessions(sessionsData.value.items)
      if (status2fa.status === 'fulfilled') setTwoFAStatus(status2fa.value)
    } catch (error) {
      console.error('Error cargando datos de seguridad:', error)
    } finally {
      setLoading(false)
    }
  }

  // --- Handlers 2FA ---

  const handle2FASetup = useCallback(async () => {
    setTwoFALoading(true)
    try {
      const data = await authService.setup2FA()
      setSetupData(data)
      setTotpCode('')
      setTwoFAView('setup')
    } catch {
      toast.error('Error al iniciar la configuración de 2FA')
    } finally {
      setTwoFALoading(false)
    }
  }, [])

  const handle2FAEnable = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (totpCode.length < 6) return
    setTwoFALoading(true)
    try {
      await authService.enable2FA(totpCode)
      // Mostrar backup codes (ya venían del setup)
      setBackupCodes(setupData?.backup_codes ?? [])
      setTwoFAView('show-backup')
      setTwoFAStatus({ enabled: true, backup_codes_remaining: setupData?.backup_codes.length ?? 0 })
      toast.success('2FA activado correctamente')
    } catch (err) {
      toast.error((err as AxiosError<{ detail?: string }>)?.response?.data?.detail || 'Código incorrecto')
      setTotpCode('')
    } finally {
      setTwoFALoading(false)
    }
  }, [totpCode, setupData])

  const handle2FADisable = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (totpCode.length < 6) return
    setTwoFALoading(true)
    try {
      await authService.disable2FA(totpCode)
      setTwoFAStatus({ enabled: false, backup_codes_remaining: 0 })
      setTwoFAView('idle')
      setTotpCode('')
      toast.success('2FA desactivado')
    } catch (err) {
      toast.error((err as AxiosError<{ detail?: string }>)?.response?.data?.detail || 'Código incorrecto')
      setTotpCode('')
    } finally {
      setTwoFALoading(false)
    }
  }, [totpCode])

  const cancelTwoFA = useCallback(() => {
    setTwoFAView('idle')
    setSetupData(null)
    setTotpCode('')
    setBackupCodes([])
  }, [])

  const copyBackupCodes = useCallback(() => {
    navigator.clipboard.writeText(backupCodes.join('\n'))
    toast.success('Códigos copiados al portapapeles')
  }, [backupCodes])

  const checkPasswordStrength = (password: string) => {
    if (!password) {
      setPasswordStrength({ strength: 0, message: '' })
      return
    }

    let strength = 0
    const issues: string[] = []

    // Longitud
    if (password.length >= policies.min_password_length) {
      strength += 20
    } else {
      issues.push(`Mínimo ${policies.min_password_length} caracteres`)
    }

    // Mayúsculas
    if (policies.require_uppercase) {
      if (/[A-Z]/.test(password)) {
        strength += 20
      } else {
        issues.push('Una mayúscula')
      }
    }

    // Números
    if (policies.require_numbers) {
      if (/\d/.test(password)) {
        strength += 20
      } else {
        issues.push('Un número')
      }
    }

    // Caracteres especiales
    if (policies.require_special_chars) {
      if (/[^A-Za-z0-9]/.test(password)) {
        strength += 20
      } else {
        issues.push('Un carácter especial')
      }
    }

    // Variedad
    if (password.length >= 12) strength += 10
    if (/[a-z]/.test(password) && /[A-Z]/.test(password)) strength += 10

    let message = ''
    if (issues.length > 0) {
      message = `Falta: ${issues.join(', ')}`
    } else if (strength >= 80) {
      message = '✓ Contraseña fuerte'
    } else if (strength >= 60) {
      message = 'Contraseña aceptable'
    }

    setPasswordStrength({ strength, message })
  }

  useEffect(() => {
    loadSecurityData()
  }, [])

  useEffect(() => {
    checkPasswordStrength(passwordData.new_password)
  }, [passwordData.new_password, policies])

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault()

    // Validaciones
    if (passwordData.new_password !== passwordData.confirm_password) {
      toast.error('Las contraseñas no coinciden')
      return
    }

    if (passwordStrength.strength < 60) {
      toast.error('La contraseña no cumple con los requisitos mínimos')
      return
    }

    try {
      setSaving(true)
      await authService.changePassword(passwordData)
      toast.success('Contraseña actualizada exitosamente')
      
      // Limpiar formulario
      setPasswordData({
        current_password: '',
        new_password: '',
        confirm_password: ''
      })
      
      onSave?.()
    } catch (error) {
      console.error('Error cambiando contraseña:', error)
      toast.error((error as AxiosError<{ detail?: string }>).response?.data?.detail || 'Error al cambiar la contraseña')
    } finally {
      setSaving(false)
    }
  }

  const handleRevokeSession = async () => {
    if (!revokeModal.sessionId || !authUser) return
    setRevokingSession(true)
    try {
      await userService.revokeUserSession(authUser.id, revokeModal.sessionId)
      toast.success('Sesión cerrada exitosamente')
      setRevokeModal({ open: false, sessionId: null, deviceName: '' })
      await loadSecurityData()
    } catch (error) {
      console.error('Error cerrando sesión:', error)
      toast.error('Error al cerrar la sesión')
    } finally {
      setRevokingSession(false)
    }
  }

  const handleRevokeAllSessions = async () => {
    if (!authUser) return
    setRevokingSession(true)
    try {
      await userService.revokeAllUserSessions(authUser.id)
      toast.success('Todas las sesiones han sido cerradas')
      setRevokeAllModal(false)
      await loadSecurityData()
    } catch (error) {
      console.error('Error cerrando sesiones:', error)
      toast.error('Error al cerrar las sesiones')
    } finally {
      setRevokingSession(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-brand-600" />
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h3 className="text-xl font-semibold text-foreground mb-2">
          Seguridad
        </h3>
        <p className="text-sm text-muted-foreground">
          Gestiona tu contraseña y sesiones activas
        </p>
      </div>

      {/* Autenticación de Doble Factor (2FA) */}
      <div className="bg-muted rounded-xl border border-border p-6">
        {/* Cabecera */}
        <div className="flex items-start justify-between">
          <div className="flex items-start space-x-3">
            <div className="bg-purple-600 text-white p-2 rounded-lg">
              <Shield size={20} />
            </div>
            <div>
              <div className="flex items-center space-x-2 mb-1">
                <h4 className="font-semibold text-foreground">
                  Autenticación de Doble Factor (2FA)
                </h4>
                {twoFAStatus?.enabled ? (
                  <span className="px-2 py-0.5 text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-full flex items-center gap-1">
                    <CheckCircle2 size={11} /> Activo
                  </span>
                ) : (
                  <span className="px-2 py-0.5 text-xs bg-muted text-muted-foreground rounded-full">
                    Inactivo
                  </span>
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                Protege tu cuenta con una app autenticadora (Google Authenticator, Authy, etc.)
              </p>
              {twoFAStatus?.enabled && (
                <p className="text-xs text-muted-foreground mt-1">
                  {twoFAStatus.backup_codes_remaining} código{twoFAStatus.backup_codes_remaining !== 1 ? 's' : ''} de respaldo restante{twoFAStatus.backup_codes_remaining !== 1 ? 's' : ''}
                </p>
              )}
            </div>
          </div>

          {/* Botón principal — solo en idle */}
          {twoFAView === 'idle' && (
            twoFAStatus?.enabled ? (
              <button
                onClick={() => { setTotpCode(''); setTwoFAView('verify-disable') }}
                className="px-3 py-1.5 text-sm text-red-600 border border-red-300 dark:border-red-700 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                Desactivar
              </button>
            ) : (
              <button
                onClick={handle2FASetup}
                disabled={twoFALoading}
                className="px-3 py-1.5 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                {twoFALoading ? <Loader2 size={14} className="animate-spin" /> : <Shield size={14} />}
                Configurar
              </button>
            )
          )}
        </div>

        {/* ── SETUP: mostrar QR + campo código ── */}
        {twoFAView === 'setup' && setupData && (
          <div className="mt-6 space-y-5">
            <div className="text-sm text-foreground/80 space-y-1">
              <p className="font-medium">Paso 1 — Escanea el código QR con tu app autenticadora:</p>
            </div>

            <div className="flex flex-col items-center gap-4">
              <img
                src={setupData.qr_code}
                alt="QR 2FA"
                className="w-44 h-44 rounded-lg border border-border bg-white p-1"
              />
              <div className="text-center">
                <p className="text-xs text-muted-foreground mb-1">Clave manual:</p>
                <code className="text-xs bg-gray-100 dark:bg-gray-900 px-3 py-1 rounded-sm font-mono tracking-widest">
                  {setupData.secret}
                </code>
              </div>
            </div>

            <form onSubmit={handle2FAEnable} className="space-y-4">
              <div>
                <p className="text-sm font-medium text-foreground/80 mb-2">
                  Paso 2 — Ingresa el código de 6 dígitos para confirmar:
                </p>
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  placeholder="000000"
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  className="w-full text-center text-2xl tracking-widest font-mono py-3 bg-card border border-input rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-foreground"
                  autoComplete="one-time-code"
                  autoFocus
                />
              </div>
              <div className="flex gap-2 justify-end">
                <button type="button" onClick={cancelTwoFA} className="px-4 py-2 text-sm text-muted-foreground border border-input rounded-lg hover:bg-muted transition-colors">
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={twoFALoading || totpCode.length < 6}
                  className="px-4 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                >
                  {twoFALoading ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                  Activar 2FA
                </button>
              </div>
            </form>
          </div>
        )}

        {/* ── SHOW BACKUP CODES ── */}
        {twoFAView === 'show-backup' && (
          <div className="mt-6 space-y-4">
            <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-300 dark:border-yellow-700 rounded-lg">
              <p className="text-sm font-semibold text-yellow-800 dark:text-yellow-300 mb-1">
                ¡Guarda estos códigos de respaldo ahora!
              </p>
              <p className="text-xs text-yellow-700 dark:text-yellow-400">
                Son de un solo uso. Si pierdes acceso a tu app autenticadora, los necesitarás para entrar.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {backupCodes.map((code) => (
                <code key={code} className="text-center text-sm font-mono bg-gray-100 dark:bg-gray-900 py-1.5 px-3 rounded-sm tracking-widest">
                  {code}
                </code>
              ))}
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={copyBackupCodes}
                className="px-4 py-2 text-sm border border-input rounded-lg hover:bg-muted transition-colors flex items-center gap-1.5"
              >
                <Copy size={14} /> Copiar
              </button>
              <button
                onClick={cancelTwoFA}
                className="px-4 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
              >
                Listo
              </button>
            </div>
          </div>
        )}

        {/* ── VERIFY DISABLE ── */}
        {twoFAView === 'verify-disable' && (
          <form onSubmit={handle2FADisable} className="mt-6 space-y-4">
            <p className="text-sm text-foreground/80">
              Ingresa el código de tu app autenticadora <span className="text-gray-500">(o un código de respaldo)</span> para desactivar el 2FA:
            </p>
            <input
              type="text"
              inputMode="numeric"
              maxLength={8}
              placeholder="000000"
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
              className="w-full text-center text-2xl tracking-widest font-mono py-3 bg-card border border-input rounded-lg focus:ring-2 focus:ring-red-500 focus:border-transparent text-foreground"
              autoComplete="one-time-code"
              autoFocus
            />
            <div className="flex gap-2 justify-end">
              <button type="button" onClick={cancelTwoFA} className="px-4 py-2 text-sm text-muted-foreground border border-input rounded-lg hover:bg-muted transition-colors">
                Cancelar
              </button>
              <button
                type="submit"
                disabled={twoFALoading || totpCode.length < 6}
                className="px-4 py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                {twoFALoading ? <Loader2 size={14} className="animate-spin" /> : <XCircle size={14} />}
                Desactivar 2FA
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Cambiar Contraseña */}
      <div className="bg-muted rounded-xl border border-border p-6">
        <div className="flex items-center space-x-3 mb-6">
          <div className="bg-brand-600 text-white p-2 rounded-lg">
            <Key size={20} />
          </div>
          <div>
            <h4 className="font-semibold text-foreground">
              Cambiar Contraseña
            </h4>
            <p className="text-sm text-muted-foreground">
              Actualiza tu contraseña regularmente para mayor seguridad
            </p>
          </div>
        </div>

        <form onSubmit={handlePasswordChange} className="space-y-4">
          {/* Contraseña Actual */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-foreground/80">
              Contraseña Actual
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
              <input
                type="password"
                value={passwordData.current_password}
                onChange={(e) => setPasswordData(prev => ({ ...prev, current_password: e.target.value }))}
                className="w-full pl-10 pr-4 py-2.5 bg-card border border-input rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent text-foreground"
                placeholder="Ingresa tu contraseña actual"
                autoComplete="new-password"
                required
              />
            </div>
          </div>

          {/* Nueva Contraseña */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-foreground/80">
              Nueva Contraseña
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
              <input
                type={showNewPassword ? 'text' : 'password'}
                value={passwordData.new_password}
                onChange={(e) => setPasswordData(prev => ({ ...prev, new_password: e.target.value }))}
                className="w-full pl-10 pr-12 py-2.5 bg-card border border-input rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent text-foreground"
                placeholder="Ingresa tu nueva contraseña"
                autoComplete="new-password"
                required
              />
              <button
                type="button"
                onClick={() => setShowNewPassword(!showNewPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                {showNewPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            
            {/* Indicador de fortaleza */}
            {passwordData.new_password && (
              <div className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">Fortaleza</span>
                  <span className={`font-medium ${
                    passwordStrength.strength >= 80 ? 'text-green-600' :
                    passwordStrength.strength >= 60 ? 'text-yellow-600' :
                    'text-red-600'
                  }`}>
                    {passwordStrength.message}
                  </span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full transition-all ${
                      passwordStrength.strength >= 80 ? 'bg-green-600' :
                      passwordStrength.strength >= 60 ? 'bg-yellow-600' :
                      'bg-red-600'
                    }`}
                    style={{ width: `${passwordStrength.strength}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Confirmar Contraseña */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-foreground/80">
              Confirmar Nueva Contraseña
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
              <input
                type={showConfirmPassword ? 'text' : 'password'}
                value={passwordData.confirm_password}
                onChange={(e) => setPasswordData(prev => ({ ...prev, confirm_password: e.target.value }))}
                className="w-full pl-10 pr-12 py-2.5 bg-card border border-input rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent text-foreground"
                placeholder="Confirma tu nueva contraseña"
                autoComplete="new-password"
                required
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            {passwordData.confirm_password && passwordData.new_password !== passwordData.confirm_password && (
              <p className="text-xs text-red-600 flex items-center space-x-1">
                <AlertTriangle size={12} />
                <span>Las contraseñas no coinciden</span>
              </p>
            )}
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={saving || passwordStrength.strength < 60}
              className="px-6 py-2.5 bg-brand-600 text-white rounded-lg hover:bg-brand-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
            >
              {saving ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Cambiando...</span>
                </>
              ) : (
                <>
                  <Key size={16} />
                  <span>Cambiar Contraseña</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Sesiones Activas */}
      <div className="bg-muted rounded-xl border border-border p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-3">
            <div className="bg-purple-600 text-white p-2 rounded-lg">
              <Laptop size={20} />
            </div>
            <div>
              <h4 className="font-semibold text-foreground">
                Sesiones Activas
              </h4>
              <p className="text-sm text-muted-foreground">
                {sessions.length} {sessions.length === 1 ? 'dispositivo conectado' : 'dispositivos conectados'}
              </p>
            </div>
          </div>
          
          {sessions.length > 1 && (
            <button
              onClick={() => setRevokeAllModal(true)}
              className="px-4 py-2 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-lg hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors flex items-center space-x-2"
            >
              <Trash2 size={16} />
              <span>Cerrar Todas</span>
            </button>
          )}
        </div>

        <div className="space-y-3">
          {sessions.map((session) => (
            <div
              key={session.id}
              className="flex items-center justify-between p-4 bg-card rounded-lg"
            >
              <div className="flex items-center space-x-3">
                {session.device_type === 'mobile' ? (
                  <Smartphone className="text-muted-foreground" size={24} />
                ) : (
                  <Laptop className="text-muted-foreground" size={24} />
                )}
                <div>
                  <p className="font-medium text-foreground">
                    {session.device_name || 'Dispositivo Desconocido'}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {session.ip_address} • {formatDateTime(session.last_activity) ?? ''}
                  </p>
                </div>
              </div>
              
              <button
                onClick={() => setRevokeModal({ open: true, sessionId: session.id, deviceName: session.device_name || 'este dispositivo' })}
                className="p-2 text-red-600 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-lg transition-colors"
                title="Cerrar sesión"
              >
                <LogOut size={18} />
              </button>
            </div>
          ))}

          {sessions.length === 0 && (
            <p className="text-center text-muted-foreground py-8">
              No hay sesiones activas
            </p>
          )}
        </div>
      </div>

      {/* Modal — cerrar sesión individual */}
      <ConfirmModal
        isOpen={revokeModal.open}
        onClose={() => setRevokeModal({ open: false, sessionId: null, deviceName: '' })}
        onConfirm={handleRevokeSession}
        title="Cerrar sesión"
        message={`¿Cerrar la sesión de ${revokeModal.deviceName}? El dispositivo perderá acceso inmediatamente.`}
        confirmText={revokingSession ? 'Cerrando...' : 'Cerrar sesión'}
        cancelText="Cancelar"
        variant="danger"
      />

      {/* Modal — cerrar todas las sesiones */}
      <ConfirmModal
        isOpen={revokeAllModal}
        onClose={() => setRevokeAllModal(false)}
        onConfirm={handleRevokeAllSessions}
        title="Cerrar todas las sesiones"
        message="Se cerrarán todas tus sesiones activas. Tendrás que iniciar sesión de nuevo en cada dispositivo."
        confirmText={revokingSession ? 'Cerrando...' : 'Cerrar todas'}
        cancelText="Cancelar"
        variant="danger"
      />
    </div>
  )
}
