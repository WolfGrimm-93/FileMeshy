"""Audit Log Schemas."""

from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from datetime import datetime
from uuid import UUID


class AuditLogBase(BaseModel):
    """Base schema para audit log."""
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    action: str = Field(..., description="CREATE, UPDATE, DELETE")
    table_name: str = Field(..., description="Nombre de la tabla afectada")
    record_id: str = Field(..., description="ID del registro afectado")
    old_data: Optional[Dict[str, Any]] = None
    new_data: Optional[Dict[str, Any]] = None
    changes: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None


class AuditLogCreate(AuditLogBase):
    """Schema para crear un registro de auditoría."""
    pass


class AuditLogList(BaseModel):
    """Schema para listar registros de auditoría."""
    id: UUID
    user_id: Optional[str]
    user_email: Optional[str]
    action: str
    table_name: str
    record_id: str
    ip_address: Optional[str]
    endpoint: Optional[str]
    method: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogDetail(AuditLogBase):
    """Schema detallado de auditoría con todos los datos."""
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogFilters(BaseModel):
    """Filtros para búsqueda de logs de auditoría."""
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    action: Optional[str] = None  # CREATE, UPDATE, DELETE
    table_name: Optional[str] = None
    record_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    search: Optional[str] = None  # Búsqueda general
    skip: int = 0
    limit: int = 50


class AuditLogResponse(BaseModel):
    """Response con datos de auditoría."""
    logs: list
    total: int
    skip: int
    limit: int
    cached: Optional[bool] = Field(default=None, description="Indica si viene de cache Redis")
