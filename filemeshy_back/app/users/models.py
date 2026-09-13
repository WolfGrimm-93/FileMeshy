from sqlalchemy import Column, String, Boolean, DateTime, func, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSON, ARRAY, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.shared.utils.uuid7 import uuid7


class User(Base):
    """Modelo de usuario."""
    __tablename__ = "users"

    __table_args__ = (
        Index('ix_user_email_active', 'email', 'is_active'),
        Index('ix_user_role_active', 'role_id', 'is_active'),
    )

    # Identificador
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    # Credenciales
    email = Column(String(255), unique=True, index=True, nullable=False)  # Email único
    hashed_password = Column(String(255), nullable=False)  # Contraseña hasheada
    
    # Historial de contraseñas (últimas 5)
    password_history = Column(ARRAY(String), default=list, nullable=True)  # Hashes de contraseñas anteriores

    # Autenticación de doble factor (2FA - TOTP)
    totp_secret = Column(String(255), nullable=True)           # Secreto TOTP cifrado con Fernet (pendiente de activar o activo) -- 255 porque el texto cifrado (~140 chars) no entra en 64
    totp_enabled = Column(Boolean, default=False, nullable=False, server_default="false")  # 2FA activo
    backup_codes = Column(ARRAY(String), default=list, nullable=True)  # Códigos de respaldo hasheados
    
    # Información personal
    first_name = Column(String(100), nullable=False)  # Nombres
    last_name = Column(String(100), nullable=True)  # Apellidos
    phone = Column(String(20), nullable=True)  # Teléfono de contacto
    avatar = Column(String(500), nullable=True)  # URL o path de la foto de perfil
    
    # Rol y permisos
    role_id = Column(UUID(as_uuid=True), ForeignKey('roles.id', ondelete='SET NULL'), nullable=True)  # FK a tabla roles -- ondelete/nullable corregidos para reflejar la BD real (users_role_id_fkey), el modelo tenia RESTRICT/NOT NULL desactualizado
    permissions = Column(JSON, default=list, nullable=False)  # Lista de permisos: ["read:customers", "write:customers", ...]
    
    # Permisos y estado
    is_active = Column(Boolean, default=True, index=True)  # Usuario activo/inactivo
    is_superuser = Column(Boolean, default=False)  # Es administrador del sistema (legacy, usar role en su lugar)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # Fecha creación
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )  # Última actualización
    last_login = Column(DateTime(timezone=True), nullable=True)  # Último inicio de sesión

    # Relaciones activas
    role_obj = relationship("Role", foreign_keys=[role_id], back_populates="users")  # Relación con tabla roles

    # Sesiones activas
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        role_name = self.role_obj.name if self.role_obj else self.role_id
        return f"<User {self.email} ({role_name})>"

