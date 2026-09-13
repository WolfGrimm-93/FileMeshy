/**
 * SISTEMA DE LOGGING
 * Registro de errores por secciones y niveles de gravedad
 */

export const LogLevel = {
  INFO: 'info',
  WARNING: 'warning',
  ERROR: 'error',
  CRITICAL: 'critical'
} as const

export type LogLevel = typeof LogLevel[keyof typeof LogLevel]

export const LogSection = {
  AUTH: 'Autenticación',
  PASSWORD_RESET: 'Restablecimiento de Contraseña',
  API: 'Comunicación con Servidor',
  UI: 'Interfaz de Usuario',
  DATA: 'Gestión de Datos',
  SYSTEM: 'Sistema'
} as const

export type LogSection = typeof LogSection[keyof typeof LogSection]

interface LogEntry {
  timestamp: string
  level: LogLevel
  section: LogSection
  message: string
  details?: string
  errorCode?: string
  userId?: string
}

class Logger {
  private logs: LogEntry[] = []
  private maxLogs = 100 // Límite de logs en memoria

  log(
    level: LogLevel,
    section: LogSection,
    message: string,
    details?: string,
    errorCode?: string
  ) {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      section,
      message,
      details,
      errorCode
    }

    this.logs.unshift(entry)
    
    // Mantener solo los últimos maxLogs
    if (this.logs.length > this.maxLogs) {
      this.logs = this.logs.slice(0, this.maxLogs)
    }

    // Logging en consola en desarrollo
    if (import.meta.env.DEV) {
      const emoji = this.getEmoji(level)
      const style = this.getStyle(level)
      
      console.log(
        `%c${emoji} [${section}] ${message}`,
        style,
        details ? `\nDetalles: ${details}` : ''
      )
    }

    // En producción, enviar logs críticos al servidor
    if (import.meta.env.PROD && level === LogLevel.CRITICAL) {
      this.sendToServer(entry)
    }
  }

  info(section: LogSection, message: string, details?: string) {
    this.log(LogLevel.INFO, section, message, details)
  }

  warning(section: LogSection, message: string, details?: string) {
    this.log(LogLevel.WARNING, section, message, details)
  }

  error(section: LogSection, message: string, details?: string, errorCode?: string) {
    this.log(LogLevel.ERROR, section, message, details, errorCode)
  }

  critical(section: LogSection, message: string, details?: string, errorCode?: string) {
    this.log(LogLevel.CRITICAL, section, message, details, errorCode)
  }

  // Obtener logs filtrados
  getLogs(section?: LogSection, level?: LogLevel): LogEntry[] {
    let filtered = this.logs

    if (section) {
      filtered = filtered.filter(log => log.section === section)
    }

    if (level) {
      filtered = filtered.filter(log => log.level === level)
    }

    return filtered
  }

  // Obtener todos los logs
  getAllLogs(): LogEntry[] {
    return this.logs
  }

  // Limpiar logs
  clearLogs() {
    this.logs = []
  }

  // Exportar logs como JSON
  exportLogs(): string {
    return JSON.stringify(this.logs, null, 2)
  }

  private getEmoji(level: LogLevel): string {
    switch (level) {
      case LogLevel.INFO:
        return 'ℹ️'
      case LogLevel.WARNING:
        return '⚠️'
      case LogLevel.ERROR:
        return '❌'
      case LogLevel.CRITICAL:
        return '🔥'
      default:
        return 'ℹ️'
    }
  }

  private getStyle(level: LogLevel): string {
    switch (level) {
      case LogLevel.INFO:
        return 'color: #3b82f6; font-weight: bold'
      case LogLevel.WARNING:
        return 'color: #f59e0b; font-weight: bold'
      case LogLevel.ERROR:
        return 'color: #ef4444; font-weight: bold'
      case LogLevel.CRITICAL:
        return 'color: #dc2626; font-weight: bold; font-size: 14px'
      default:
        return 'color: #3b82f6; font-weight: bold'
    }
  }

  private async sendToServer(_entry: LogEntry) {
    try {
      // Implementar envío al servidor si es necesario
      // await fetch('/api/v1/logs', { method: 'POST', body: JSON.stringify(entry) })
    } catch (error) {
      // Evitar loops infinitos de logging
      console.error('Error al enviar log al servidor:', error)
    }
  }
}

// Instancia singleton
export const logger = new Logger()
