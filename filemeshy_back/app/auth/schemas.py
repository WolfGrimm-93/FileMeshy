"""Schemas del módulo auth: sesiones, y las 3 fases de reset de contraseña
(request/verify/confirm) con sus códigos de error específicos."""

from pydantic import BaseModel, EmailStr, field_validator, model_validator
from datetime import datetime
from typing import Optional
from uuid import UUID
import re


# ========================================================================
# SESIONES
# ========================================================================

def _parse_user_agent(ua: Optional[str]) -> tuple[str, str]:
    """
    Parsea el user_agent y retorna (device_type, device_name).
    device_type: 'mobile' | 'desktop'
    device_name: nombre legible del navegador/SO
    """
    if not ua:
        return "desktop", "Dispositivo desconocido"

    ua_lower = ua.lower()

    # Detectar tipo de dispositivo
    is_mobile = any(k in ua_lower for k in ("mobile", "android", "iphone", "ipad", "ipod"))
    device_type = "mobile" if is_mobile else "desktop"

    # Detectar navegador
    if "firefox" in ua_lower:
        browser = "Firefox"
    elif "edg/" in ua_lower or "edge/" in ua_lower:
        browser = "Edge"
    elif "chrome" in ua_lower and "chromium" not in ua_lower:
        browser = "Chrome"
    elif "safari" in ua_lower and "chrome" not in ua_lower:
        browser = "Safari"
    elif "opera" in ua_lower or "opr/" in ua_lower:
        browser = "Opera"
    elif "tauri" in ua_lower:
        browser = "App FileMeshy"
    else:
        browser = "Navegador desconocido"

    # Detectar SO
    if "windows nt 10" in ua_lower or "windows nt 11" in ua_lower:
        os_name = "Windows 10/11"
    elif "windows nt" in ua_lower:
        os_name = "Windows"
    elif "mac os x" in ua_lower or "macos" in ua_lower:
        os_name = "macOS"
    elif "android" in ua_lower:
        os_name = "Android"
    elif "iphone" in ua_lower or "ipad" in ua_lower:
        os_name = "iOS"
    elif "linux" in ua_lower:
        os_name = "Linux"
    else:
        os_name = "SO desconocido"

    return device_type, f"{browser} en {os_name}"


class SessionBase(BaseModel):
    """Schema base para sesión."""
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class SessionResponse(SessionBase):
    """Schema de sesión para respuesta."""
    id: UUID
    user_id: UUID
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    is_active: bool
    device_type: Optional[str] = None
    device_name: Optional[str] = None

    @model_validator(mode="after")
    def populate_device_info(self) -> "SessionResponse":
        self.device_type, self.device_name = _parse_user_agent(self.user_agent)
        return self

    class Config:
        from_attributes = True


class SessionsListResponse(BaseModel):
    """Respuesta con lista de sesiones."""
    items: list[SessionResponse]
    total: int


# ========================================================================
# PASSWORD RESET — PASOS 1/2/3
# ========================================================================

class PasswordResetRequest(BaseModel):
    """
    🔐 PASO 1: Solicitud de código

    Endpoint: POST /password-reset/request
    """
    email: EmailStr


class PasswordResetVerify(BaseModel):
    """
    🔐 PASO 2: Verificación del código

    Endpoint: POST /password-reset/verify
    - Recibe: {"code": "123456"}
    - Responde: {"reset_token": "..."}
    """
    code: str  # Obligatorio en PASO 2

    @field_validator('code')
    @classmethod
    def validate_code(cls, v: str) -> str:
        """Valida formato del código (6 dígitos)."""
        if not v.isdigit() or len(v) != 6:
            raise ValueError('El código debe tener exactamente 6 dígitos')
        return v


class PasswordResetConfirm(BaseModel):
    """
    🔐 PASO 3: Confirmación y cambio de contraseña

    Endpoint: POST /password-reset/confirm
    - Recibe: {"new_password": "...", "reset_token": "..."}
    - Responde: {"message": "..."}
    """
    new_password: str  # Obligatorio en PASO 3
    reset_token: Optional[str] = None  # Legacy: se acepta en body si no viene por cookie

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Valida la seguridad de la contraseña."""
        if len(v) < 8:
            raise ValueError('La contraseña debe tener al menos 8 caracteres')
        if not re.search(r'[A-Z]', v):
            raise ValueError('La contraseña debe contener al menos una mayúscula')
        if not re.search(r'[a-z]', v):
            raise ValueError('La contraseña debe contener al menos una minúscula')
        if not re.search(r'\d', v):
            raise ValueError('La contraseña debe contener al menos un número')
        return v


class PasswordResetResponse(BaseModel):
    """Schema para respuesta de solicitud de reset."""
    message: str
    email: str
    expires_in_minutes: int = 30


class PasswordResetCode(BaseModel):
    """Schema para código de reset (BD)."""
    id: UUID
    user_id: UUID
    email: str
    code: str
    expires_at: datetime
    is_used: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ========================================================================
# PASSWORD RESET — CÓDIGOS DE ERROR
# ========================================================================
# Define códigos de error específicos para que el frontend pueda manejarlos
# correctamente.

class PasswordResetErrorCode:
    """Códigos de error para password reset"""

    # PASO 1: Request
    INVALID_EMAIL = "invalid_email"
    EMAIL_NOT_FOUND = "email_not_found"

    # PASO 2: Verify
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_EXPIRED = "session_expired"
    INVALID_CODE = "invalid_code"
    MAX_ATTEMPTS_EXCEEDED = "max_attempts_exceeded"
    CODE_EXPIRED = "code_expired"

    # PASO 3: Confirm
    INVALID_TOKEN = "invalid_token"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_ALREADY_USED = "token_already_used"
    INVALID_PASSWORD = "invalid_password"
    PASSWORD_REUSED = "password_reused"
    USER_NOT_FOUND = "user_not_found"


class PasswordResetError(BaseModel):
    """Estructura de error específica para password reset"""
    status: int
    code: str  # Código de error específico (ej: "session_expired", "invalid_code", etc)
    message: str  # Mensaje legible para el usuario
    detail: Optional[str] = None  # Detalles técnicos (opcional)


# Mapeo de códigos de error a mensajes
ERROR_MESSAGES = {
    # PASO 1
    PasswordResetErrorCode.INVALID_EMAIL: "El correo electrónico no es válido",
    PasswordResetErrorCode.EMAIL_NOT_FOUND: "No Existe esta cuenta de correo electrónico",

    # PASO 2
    PasswordResetErrorCode.SESSION_NOT_FOUND: "Sesión no encontrada. Solicita un código nuevo",
    PasswordResetErrorCode.SESSION_EXPIRED: "Sesión expirada. Solicita un código nuevo",
    PasswordResetErrorCode.INVALID_CODE: "El código ingresado no es válido",
    PasswordResetErrorCode.MAX_ATTEMPTS_EXCEEDED: "Demasiados intentos fallidos. Solicita un código nuevo",
    PasswordResetErrorCode.CODE_EXPIRED: "El código ha expirado. Solicita uno nuevo",

    # PASO 3
    PasswordResetErrorCode.INVALID_TOKEN: "El token es inválido. Solicita un código nuevo",
    PasswordResetErrorCode.TOKEN_EXPIRED: "El token ha expirado. Solicita un código nuevo",
    PasswordResetErrorCode.TOKEN_ALREADY_USED: "El token ya fue utilizado. Solicita un código nuevo",
    PasswordResetErrorCode.INVALID_PASSWORD: "La contraseña no cumple los requisitos de seguridad",
    PasswordResetErrorCode.PASSWORD_REUSED: "No puedes usar una contraseña anterior",
    PasswordResetErrorCode.USER_NOT_FOUND: "Usuario no encontrado",
}
