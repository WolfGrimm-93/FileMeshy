"""Schemas de la API de plataforma (Fase 3 -- alta y config de tenants).

Ver Obsidian "Desarrollo/Plataforma - Administracion de Tenants" para el
diseño completo (alcance, decisión de arquitectura, endpoints planeados).
"""

from datetime import datetime
from typing import Optional
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
    # `provisionar_tenant()` (app/tenants/service.py) YA devuelve este campo en
    # su dict de resultado (la credencial del super admin recién generada,
    # única vez que se puede mostrar) -- faltaba acá en el schema de salida,
    # así que `TenantCreateResponse(**resultado)` lo descartaba en silencio
    # (Pydantic ignora por defecto los campos del dict que el modelo no
    # declara). Hallazgo de QA en vivo del frontend: el modal de credenciales
    # del panel quedaba con el email vacío después de crear un tenant real.
    admin_email: str


class TenantUpdateRequest(BaseModel):
    """PATCH parcial -- ambos campos opcionales, pero al menos uno tiene que venir.

    La validación de "al menos un campo" NO se hace acá con @model_validator
    (a diferencia de TenantCreateRequest.rechazar_schema_reservado más arriba):
    un ValueError ahí lo dispara Pydantic DURANTE el parseo del body, antes de
    que la request llegue siquiera al router -- y FastAPI lo traduce siempre a
    422, nunca al 400 que pide el contrato de este endpoint (un PATCH `{}` es
    un error de uso/negocio -- "no pediste cambiar nada" -- no un error de
    forma/tipo de dato). Por eso queda como un método simple que el router
    llama a mano y convierte en HTTPException(400, ...) él mismo."""
    is_active: Optional[bool] = None
    plan: Optional[str] = Field(default=None, max_length=32)

    def tiene_algun_campo(self) -> bool:
        return self.is_active is not None or self.plan is not None


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
