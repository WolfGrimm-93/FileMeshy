"""Audit Log Model - Sistema de auditoría completo."""

from sqlalchemy import Column, String, Text, DateTime, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base
from app.shared.utils.uuid7 import uuid7


class AuditLog(Base):
    """
    Registro de auditoría para todas las operaciones del sistema.

    Captura automáticamente:
    - CREATE: Creación de registros
    - UPDATE: Modificación de registros
    - DELETE: Eliminación de registros
    """
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    # Información del usuario
    user_id = Column(String, nullable=True, index=True)  # ID del usuario que realizó la acción
    user_email = Column(String, nullable=True)  # Email del usuario

    # Información de la acción
    action = Column(String(20), nullable=False, index=True)  # CREATE, UPDATE, DELETE, SWITCH_USER...
    table_name = Column(String(100), nullable=False, index=True)  # Tabla afectada
    record_id = Column(String(100), nullable=False, index=True)  # ID del registro afectado

    # Datos de la operación
    old_data = Column(JSON, nullable=True)  # Datos antes del cambio (para UPDATE/DELETE)
    new_data = Column(JSON, nullable=True)  # Datos después del cambio (para CREATE/UPDATE)
    changes = Column(JSON, nullable=True)  # Solo campos que cambiaron (para UPDATE)

    # Información de contexto
    ip_address = Column(String(45), nullable=True)  # IPv4 o IPv6
    user_agent = Column(Text, nullable=True)  # User agent del navegador
    endpoint = Column(String(255), nullable=True)  # Endpoint que ejecutó la acción
    method = Column(String(10), nullable=True)  # HTTP method (POST, PUT, DELETE)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Índices compuestos para consultas comunes
    __table_args__ = (
        Index('idx_audit_user_table', 'user_id', 'table_name'),
        Index('idx_audit_table_record', 'table_name', 'record_id'),
        Index('idx_audit_action_date', 'action', 'created_at'),
        Index('idx_audit_table_date', 'table_name', 'created_at'),
    )

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action={self.action}, table={self.table_name}, record={self.record_id})>"
