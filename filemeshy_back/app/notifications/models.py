"""Modelo de Notificación del sistema."""

from sqlalchemy import Column, String, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
from app.shared.utils.uuid7 import uuid7


class Notification(Base):
    """Modelo de notificación para usuarios del sistema."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notification_user_read", "user_id", "is_read"),
        Index("ix_notification_user_created", "user_id", "created_at"),
        Index("ix_notification_type", "type"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    # Usuario destinatario
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Contenido
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)

    # Clasificación
    type = Column(String(50), nullable=False, index=True)  # stock_bajo, pago_vencido, nueva_venta, seguridad, sistema
    severity = Column(String(20), nullable=False, default="info")  # info, warning, error, success

    # Estado
    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime, nullable=True)

    # Navegación (ruta del frontend para ver el detalle)
    action_url = Column(String(500), nullable=True)

    # Datos adicionales (JSON flexible para contexto extra)
    extra_data = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # Relación
    user = relationship("User", backref="notifications", lazy="select")
