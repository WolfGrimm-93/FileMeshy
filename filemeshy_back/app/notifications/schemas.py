"""Schemas de Notificación para validación y serialización."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
from uuid import UUID


class NotificationType(str, Enum):
    """Tipos de notificación del sistema."""
    SEGURIDAD = "seguridad"
    SISTEMA = "sistema"
    ALMACENAMIENTO = "almacenamiento"
    COMPARTIDO = "compartido"


class NotificationSeverity(str, Enum):
    """Niveles de severidad de notificación."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


# ==================== Schemas de respuesta ====================

class NotificationResponse(BaseModel):
    """Schema de respuesta para una notificación."""
    id: UUID
    user_id: UUID
    title: str
    message: str
    type: str
    severity: str
    is_read: bool
    read_at: Optional[datetime] = None
    action_url: Optional[str] = None
    extra_data: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """Respuesta paginada de notificaciones."""
    items: List[NotificationResponse]
    total: int
    unread_count: int
    page: int
    page_size: int
    total_pages: int


class UnreadCountResponse(BaseModel):
    """Conteo de notificaciones no leídas."""
    unread_count: int


# ==================== Schemas de creación (interno) ====================

class NotificationCreate(BaseModel):
    """Schema para crear una notificación (uso interno del backend)."""
    user_id: UUID
    title: str = Field(..., max_length=255)
    message: str
    type: NotificationType
    severity: NotificationSeverity = NotificationSeverity.INFO
    action_url: Optional[str] = Field(None, max_length=500)
    extra_data: Optional[dict] = None


# ==================== Schemas de actualización ====================

class NotificationMarkRead(BaseModel):
    """Schema para marcar notificaciones como leídas."""
    notification_ids: Optional[List[UUID]] = None  # None = marcar todas
