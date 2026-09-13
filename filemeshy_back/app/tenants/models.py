"""Tenant model (fundación multi-tenancy fase 2)."""

from sqlalchemy import Boolean, Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.shared.utils.uuid7 import uuid7


class Tenant(Base):
    """Empresa cliente en modo cloud (una fila por instalación, schema propio)."""

    __tablename__ = "tenants"

    # Identificador (UUID v7 generado en Python, nunca server_default)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    # Identificador público (usado en URLs, headers) - con guiones permitidos
    slug = Column(String(64), nullable=False, unique=True, index=True)

    # Identificador interno del schema PostgreSQL - sin guiones, usado como identificador SQL
    schema_name = Column(String(63), nullable=False, unique=True)

    company_name = Column(String(255), nullable=False)
    plan = Column(String(32), nullable=False, default="standard", server_default="standard")

    is_active = Column(Boolean, nullable=False, default=True, server_default="true")

    custom_domain = Column(String(255), nullable=True, unique=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
