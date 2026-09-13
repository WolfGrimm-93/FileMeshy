/**
 * UTILIDADES DE LOGGING
 * Funciones helper para consultar logs en la consola del navegador
 */

import { logger, LogLevel, LogSection } from './logger'

// Declaración de tipos para window.logs
declare global {
  interface Window {
    logs?: {
      all: () => unknown[]
      section: (section: LogSection) => unknown[]
      level: (level: LogLevel) => unknown[]
      errors: () => unknown[]
      passwordReset: () => unknown[]
      auth: () => unknown[]
      api: () => unknown[]
      system: () => unknown[]
      export: () => string
      clear: () => void
      help: () => void
    }
  }
}

// Agregar funciones globales en desarrollo para facilitar debugging
if (import.meta.env.DEV) {
  window.logs = {
    // Ver todos los logs
    all: () => {
      console.table(logger.getAllLogs())
      return logger.getAllLogs()
    },

    // Ver logs por sección
    section: (section: LogSection) => {
      const filtered = logger.getLogs(section)
      console.table(filtered)
      return filtered
    },

    // Ver logs por nivel
    level: (level: LogLevel) => {
      const filtered = logger.getLogs(undefined, level)
      console.table(filtered)
      return filtered
    },

    // Ver solo errores
    errors: () => {
      const errors = logger.getLogs(undefined, LogLevel.ERROR)
      const critical = logger.getLogs(undefined, LogLevel.CRITICAL)
      const allErrors = [...errors, ...critical]
      console.table(allErrors)
      return allErrors
    },

    // Ver logs de una sección específica
    passwordReset: () => {
      const logs = logger.getLogs(LogSection.PASSWORD_RESET)
      console.table(logs)
      return logs
    },

    auth: () => {
      const logs = logger.getLogs(LogSection.AUTH)
      console.table(logs)
      return logs
    },

    api: () => {
      const logs = logger.getLogs(LogSection.API)
      console.table(logs)
      return logs
    },

    system: () => {
      const logs = logger.getLogs(LogSection.SYSTEM)
      console.table(logs)
      return logs
    },

    // Exportar logs como JSON
    export: () => {
      const json = logger.exportLogs()
      console.log(json)
      // Copiar al portapapeles
      navigator.clipboard.writeText(json).then(() => {
        console.log('✅ Logs copiados al portapapeles')
      })
      return json
    },

    // Limpiar todos los logs
    clear: () => {
      logger.clearLogs()
      console.log('🧹 Logs limpiados')
    },

    // Ayuda
    help: () => {
      console.log(`
📊 Sistema de Logging - Comandos Disponibles:

🔍 Consultar Logs:
  logs.all()              - Ver todos los logs
  logs.errors()           - Ver solo errores y críticos
  logs.section(section)   - Filtrar por sección
  logs.level(level)       - Filtrar por nivel de gravedad

📂 Por Sección:
  logs.passwordReset()    - Logs de restablecimiento de contraseña
  logs.auth()             - Logs de autenticación
  logs.api()              - Logs de comunicación con API
  logs.system()           - Logs del sistema

🛠️ Utilidades:
  logs.export()           - Exportar logs como JSON (copia al portapapeles)
  logs.clear()            - Limpiar todos los logs
  logs.help()             - Mostrar esta ayuda

📌 Secciones disponibles:
  ${Object.values(LogSection).join(', ')}

📊 Niveles de gravedad:
  ${Object.values(LogLevel).join(', ')}
      `)
    }
  }

  console.log(`
%c📊 Sistema de Logging Activo%c
Escribe %clogs.help()%c en la consola para ver los comandos disponibles.
  `, 
    'color: #3A64D9; font-weight: bold; font-size: 16px',
    '',
    'color: #3b82f6; font-weight: bold',
    ''
  )
}

export {}
