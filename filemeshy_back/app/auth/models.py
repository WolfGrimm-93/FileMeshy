"""Modelos del módulo auth: Session (tracking de sesiones activas) y
PasswordResetSession (sesión temporal opaca para reset de contraseña)."""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.core.database import Base
from app.shared.utils.uuid7 import uuid7


class Session(Base):
    """Modelo para tracking de sesiones activas de usuarios."""
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # JTI (JWT ID) únicos para cada token
    access_token_jti = Column(String(36), nullable=False, unique=True, index=True)
    refresh_token_jti = Column(String(36), nullable=False, unique=True, index=True)

    # Información de la sesión
    ip_address = Column(String(45), nullable=True)  # IPv4 o IPv6
    user_agent = Column(String(500), nullable=True)  # Navegador/dispositivo

    # Control de tiempo
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_activity = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)  # Cuando expira el refresh token

    # Estado
    is_active = Column(Boolean, default=True, nullable=False)

    # Relación con usuario
    user = relationship("User", back_populates="sessions")

    def __repr__(self):
        return f"<Session(id={self.id}, user_id={self.user_id}, active={self.is_active})>"


class PasswordResetSession(Base):
    """
    Sesión temporal opaca para reset de contraseña.

    FLUJO:
    1. /request → crea sesión, envía código por email
    2. /verify → valida código hash, genera reset_token JWT
    3. /confirm → valida token, cambia password
    """
    __tablename__ = "password_reset_sessions"

    # Identificador
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    # Session ID opaco (UUID) - lo que va en la cookie
    session_id = Column(String(36), nullable=False, unique=True, index=True)

    # Relación con usuario
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # Email del usuario (para verificación)
    email = Column(String(255), nullable=False, index=True)

    # HASH del código (nunca guardamos el código plano)
    code_hash = Column(String(255), nullable=False)

    # Intentos fallidos en /verify
    code_attempts = Column(Integer, default=0)

    # Expiración de la sesión (15 minutos)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Si el código ya fue validado
    code_verified = Column(Boolean, default=False)

    # Si la sesión fue usada para cambiar password (uso único)
    is_used = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def is_expired(self) -> bool:
        """Verifica si la sesión ha expirado."""
        return datetime.now(timezone.utc) > self.expires_at

    def __repr__(self):
        return f"<PasswordResetSession {self.session_id[:8]}... - {self.email}>"
