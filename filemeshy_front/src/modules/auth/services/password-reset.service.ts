/**
 * Servicio de restablecimiento de contraseña
 * 
 * 🔐 FLUJO SEGURO DE 3 PASOS:
 * 
 * 1️⃣ POST /password-reset/request
 *    - Frontend: envía email
 *    - Backend: genera código, envía por email, guardia HASH en BD
 *    - Cookie: password_reset_session (opaco, UUID)
 * 
 * 2️⃣ POST /password-reset/verify
 *    - Frontend: envía código (validado contra HASH)
 *    - Backend: valida código, invalida código, genera reset_token JWT
 *    - Respuesta: reset_token (JSON Web Token con TTL 5 min)
 * 
 * 3️⃣ POST /password-reset/confirm
 *    - Frontend: envía reset_token + nueva_password
 *    - Backend: valida token, cambia password, invalida token (uso único)
 *    - Respuesta: success
 */

import { apiClient } from '@/shared/config/api'

// ===== CÓDIGOS DE ERROR =====
export const PASSWORD_RESET_ERROR_CODES = {
  // PASO 2: Verify
  SESSION_NOT_FOUND: 'session_not_found',
  SESSION_EXPIRED: 'session_expired',
  INVALID_CODE: 'invalid_code',
  MAX_ATTEMPTS_EXCEEDED: 'max_attempts_exceeded',
  CODE_EXPIRED: 'code_expired',
  
  // PASO 3: Confirm
  INVALID_TOKEN: 'invalid_token',
  TOKEN_EXPIRED: 'token_expired',
  TOKEN_ALREADY_USED: 'token_already_used',
  INVALID_PASSWORD: 'invalid_password',
  PASSWORD_REUSED: 'password_reused',
  USER_NOT_FOUND: 'user_not_found',
}

// ===== TIPOS =====

export interface PasswordResetResponse {
  message: string
  expires_in_minutes?: number
}

export interface PasswordResetVerifyResponse {
  message: string
}

export interface PasswordResetConfirmResponse {
  message: string
}

export interface PasswordResetErrorResponse {
  status: number
  code: string  // Código de error específico
  message: string
  detail?: string
}

// ===== SERVICE =====

class PasswordResetService {
  private basePath = '/auth'

  /**
   * 🔐 PASO 1: Solicitar código de restablecimiento de contraseña
   * 
   * @param email - Email del usuario
   * @returns Respuesta con mensaje y tiempo de expiración
   * 
   * SEGURIDAD:
   * - Respuesta idéntica si usuario existe o no
   * - Código enviado SOLO por email
   * - Código nunca en respuesta JSON
   * - Cookie session_id opaco (identificador temporal)
   */
  async requestPasswordReset(email: string): Promise<PasswordResetResponse> {
    const response = await apiClient.post<{ expires_in_minutes: number }>(
      `${this.basePath}/password-reset/request`,
      { email }
    )
    return {
      message: 'Si el email existe, recibirás un código',
      expires_in_minutes: response.expires_in_minutes
    }
  }

  /**
   * 🔐 PASO 2: Verificar código y obtener reset_token JWT
   * 
   * @param code - Código de 6 dígitos del email
   * @returns Objeto con reset_token (JWT temporal)
   * 
   * SEGURIDAD:
   * - Valida código contra HASH en BD
   * - Máximo 5 intentos, luego bloquea
   * - Invalida código inmediatamente (uso único)
   * - Genera JWT con TTL corto (5 minutos)
   * - JWT tiene scope: "password_reset"
   */
  async verifyCode(code: string): Promise<PasswordResetVerifyResponse> {
    await apiClient.post(
      `${this.basePath}/password-reset/verify`,
      { code }
    )
    return {
      message: 'Código verificado. Establece tu nueva contraseña',
    }
  }

  /**
   * 🔐 PASO 3: Confirmar nuevo password con reset_token
   * 
   * @param newPassword - Nueva contraseña
   * @param resetToken - JWT del PASO 2 (reset_token)
   * @returns Respuesta de éxito
   * 
   * SEGURIDAD:
   * - Valida firma del JWT
   * - Valida expiración (5 min)
   * - Valida scope === "password_reset"
   * - Valida complejidad de nueva password
   * - Cambia password con bcrypt
   * - Invalida token (uso único)
   * - Invalida todas las sesiones activas del usuario
   */
  async confirmPasswordReset(
    newPassword: string
  ): Promise<PasswordResetConfirmResponse> {
    const response = await apiClient.post<{ message: string }>(
      `${this.basePath}/password-reset/confirm`,
      { new_password: newPassword }
    )
    return {
      message: response.message || 'Contraseña actualizada exitosamente'
    }
  }

  /**
   * Validar que el código tenga el formato correcto (6 dígitos)
   * 
   * @param code - Código a validar
   * @returns true si el código es válido
   */
  validateCode(code: string): boolean {
    return /^\d{6}$/.test(code)
  }

  /**
   * Validar email (formato básico)
   * 
   * @param email - Email a validar
   * @returns true si el email es válido
   */
  validateEmail(email: string): boolean {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
  }

  /**
   * Validar contraseña
   * 
   * Requisitos:
   * - Mínimo 8 caracteres
   * - Al menos una mayúscula (A-Z)
   * - Al menos una minúscula (a-z)
   * - Al menos un número (0-9)
   * 
   * @param password - Contraseña a validar
   * @returns Objeto con validación y mensaje
   */
  validatePassword(password: string): { valid: boolean; error?: string } {
    if (!password) {
      return { valid: false, error: 'La contraseña es requerida' }
    }

    if (password.length < 8) {
      return { valid: false, error: 'Mínimo 8 caracteres' }
    }

    if (!/[A-Z]/.test(password)) {
      return { valid: false, error: 'Debe tener al menos una mayúscula (A-Z)' }
    }

    if (!/[a-z]/.test(password)) {
      return { valid: false, error: 'Debe tener al menos una minúscula (a-z)' }
    }

    if (!/\d/.test(password)) {
      return { valid: false, error: 'Debe tener al menos un número (0-9)' }
    }

    return { valid: true }
  }
}

export const passwordResetService = new PasswordResetService()
