from __future__ import annotations

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum
from uuid import UUID


# ===== ENUMS =====
class UserRole(str, Enum):
    """Roles de usuario disponibles."""
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    USER = "USER"


# ===== USER SCHEMAS =====
class UserBase(BaseModel):
    """Schema base para usuarios."""
    email: EmailStr
    first_name: str
    last_name: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None
    is_active: bool = True


class UserCreate(UserBase):
    """Schema para crear usuarios."""
    password: str
    role_id: Optional[UUID] = None  # Si no se especifica, el CRUD asigna el rol USER por nombre
    turnstile_token: Optional[str] = None  # Solo lo usa POST /auth/register (ver auth/router.py)


class UserUpdate(BaseModel):
    """Schema para actualizar usuarios."""
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
    role_id: Optional[UUID] = None
    permissions: Optional[List[str]] = None


class User(UserBase):
    """Schema de usuario con datos de BD."""
    id: UUID
    role_id: Optional[UUID] = None
    role: Optional[str] = None  # Computed: se llena desde role_obj.name
    permissions: List[str] = []
    theme: Optional[str] = None  # Tema del usuario (light, dark, auto)
    sesiones_activas: int = 0  # Número de sesiones activas
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

    @field_validator("avatar", mode="before")
    @classmethod
    def normalize_avatar_url(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        from app.files.service import get_public_url
        return get_public_url(v)

    class Config:
        from_attributes = True


# ===== PAGINATION =====
class UsersResponse(BaseModel):
    """Respuesta paginada de usuarios."""
    items: List[User]
    total: int
    page: int
    page_size: int
    total_pages: int
    cached: bool = False


# ===== AUTH SCHEMAS =====
class LoginRequest(BaseModel):
    """Schema para login."""
    email: EmailStr
    password: str
    remember_me: bool = False
    turnstile_token: Optional[str] = None


class TokenResponse(BaseModel):
    """Schema para respuesta de token."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: User


class RefreshTokenRequest(BaseModel):
    """Schema para refrescar token. refresh_token es opcional -- en web viaja
    en la cookie httpOnly; solo la app de escritorio (cross-origin, la cookie
    SameSite=lax nunca le llega) lo manda explicito en el body."""
    refresh_token: Optional[str] = None


# ===== 2FA SCHEMAS =====
class TwoFactorSetupResponse(BaseModel):
    """Respuesta al iniciar configuración de 2FA."""
    qr_code: str        # Imagen QR en base64 (data:image/png;base64,...)
    secret: str         # Secreto para entrada manual en la app autenticadora
    backup_codes: List[str]  # Códigos de respaldo (mostrar UNA sola vez)


class TwoFactorStatus(BaseModel):
    """Estado actual del 2FA del usuario."""
    enabled: bool
    backup_codes_remaining: int = 0


class TwoFactorVerifyRequest(BaseModel):
    """Código TOTP para verificar y activar 2FA."""
    code: str


class TwoFactorDisableRequest(BaseModel):
    """Código TOTP o backup code para desactivar 2FA."""
    code: str


class TwoFactorLoginResponse(BaseModel):
    """Respuesta cuando se requiere 2FA para completar el login."""
    requires_2fa: bool = True
    pre_auth_token: str  # JWT de corta vida (5 min) para completar el login


class TwoFactorLoginVerify(BaseModel):
    """Request para completar el login con código TOTP."""
    pre_auth_token: str
    code: str
