"""Schemas de la API de plataforma (Fase 3 -- alta y config de tenants).

Ver Obsidian "Desarrollo/Plataforma - Administracion de Tenants" para el
diseño completo (alcance, decisión de arquitectura, endpoints planeados).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.tenants.service import SCHEMA_NAMES_RESERVADOS

# Mismos patrones que los CHECK constraints de la migración 0047_create_tenants_table
# y que TenantMiddleware.SLUG_RE (app/shared/middleware/tenant.py) -- validar acá también
# para rechazar en el borde de la API, no solo cuando ya es tarde en Postgres.
SLUG_PATTERN = r"^[a-z][a-z0-9-]{1,62}$"
SCHEMA_NAME_PATTERN = r"^[a-z][a-z0-9_]{2,62}$"


class TenantCreateRequest(BaseModel):
    slug: str = Field(..., pattern=SLUG_PATTERN, description="Identificador público (URLs/headers), ej. 'acme-corp'")
    schema_name: str = Field(..., pattern=SCHEMA_NAME_PATTERN, description="Nombre de schema PostgreSQL, ej. 'tenant_acme_corp'")
    company_name: str = Field(..., min_length=1, max_length=255, description="Razón social / nombre comercial")
    plan: str = Field(default="standard", max_length=32)

    @field_validator("schema_name")
    @classmethod
    def rechazar_schema_reservado(cls, v: str) -> str:
        if v in SCHEMA_NAMES_RESERVADOS or v.startswith("pg_"):
            raise ValueError(
                f"'{v}' es un nombre de schema reservado/ya-existente en Postgres -- "
                "no se puede usar para un tenant."
            )
        return v


class TenantCreateResponse(BaseModel):
    tenant_id: UUID
    slug: str
    schema_name: str


class TenantListItem(BaseModel):
    id: UUID
    slug: str
    schema_name: str
    company_name: str
    plan: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
