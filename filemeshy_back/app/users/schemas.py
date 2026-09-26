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


AVATAR_MAX_LENGTH = 500  # = longitud de la columna users.avatar


def validate_avatar_reference(v: Optional[str]) -> Optional[str]:
    """Un `avatar` entrante solo puede ser una CLAVE/URL de storage (lo que devuelve
    POST /users/{id}/avatar), nunca contenido: rechaza data-URIs/base64 (antes
    superaban VARCHAR(500) -> 500) con un mensaje que indica el endpoint correcto.
    `None`/"" borra la foto."""
    if v is None:
        return None
    v = v.strip()
    if v == "":
        return None
    if v.lower().startswith("data:") or ";base64," in v[:100].lower():
        raise ValueError(
            "El avatar no puede enviarse como data-URI/base64. Subí la imagen con "
            "POST /api/v1/users/{user_id}/avatar (multipart, campo 'file')."
        )
    if len(v) > AVATAR_MAX_LENGTH:
        raise ValueError(f"El avatar no puede superar {AVATAR_MAX_LENGTH} caracteres (referencia a storage)")
    if any(ch.isspace() or ord(ch) < 32 for ch in v):
        raise ValueError("El avatar contiene caracteres no válidos")
    from app.files.service import is_minio_url

    # Clave de storage, URL de NUESTRO storage o ruta local /static/...
    if not (is_minio_url(v) or v.startswith("/static/")):
        raise ValueError("El avatar debe ser una referencia al storage; subí la imagen con POST /api/v1/users/{user_id}/avatar")
    return v


class UserCreate(UserBase):
    """Schema para crear usuarios."""
    password: str
    role_id: Optional[UUID] = None  # Si no se especifica, el CRUD asigna el rol USER por nombre
    turnstile_token: Optional[str] = None  # Solo lo usa POST /auth/register (ver auth/router.py)

    @field_validator("avatar")
    @classmethod
    def _no_avatar_on_create(cls, v: Optional[str]) -> Optional[str]:
        # Ronda 12c: al crear un usuario no puede existir aún un objeto de avatar propio;
        # aceptar una referencia arbitraria abría un IDOR de storage. Se sube con
        # POST /api/v1/users/{user_id}/avatar.
        if v is not None and v.strip() != "":
            raise ValueError("No se puede fijar el avatar al crear el usuario. Subí la imagen con POST /api/v1/users/{user_id}/avatar (multipart, campo 'file').")
        return None


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

    @field_validator("avatar")
    @classmethod
    def _check_avatar(cls, v: Optional[str]) -> Optional[str]:
        return validate_avatar_reference(v)


class User(UserBase):
    """Schema de usuario con datos de BD (SALIDA).

    `email` es `str` a propósito: la validación de EmailStr es cosa de los
    schemas de ENTRADA (UserCreate/UserUpdate/LoginRequest). Validarla al
    serializar datos ya guardados rompía el listado completo (500) por un solo
    usuario legado con dominio reservado (ej. *.local)."""
    email: str
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
