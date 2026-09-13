"""Schemas de cuota de almacenamiento para validación y serialización.

Contrato de API acordado con el frontend (pantalla admin de cuotas) -- los
nombres y tipos de estos schemas NO son de libre elección, tienen que
coincidir exacto con lo que el frontend ya está construyendo en paralelo.
"""

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class StorageQuotaItem(BaseModel):
    """Un usuario + su cuota de almacenamiento (fila de la tabla admin)."""
    user_id: UUID
    email: str
    first_name: str
    last_name: str
    limit_bytes: Optional[int] = None
    bytes_used: int

    class Config:
        from_attributes = True


class StorageQuotaListResponse(BaseModel):
    """Mismo shape de paginación que `UsersResponse` (ver app/users/schemas.py)."""
    items: List[StorageQuotaItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class StorageQuotaUpdate(BaseModel):
    """Body de `PUT /storage-quotas/{user_id}`. `limit_bytes: null` = sin límite."""
    limit_bytes: Optional[int] = None


class StorageCapacityResponse(BaseModel):
    """Capacidad real de disco del volumen de MinIO (`GET /storage-quotas/capacity`).

    Cualquier campo puede venir en `None` si no se pudo leer la info real de
    MinIO (endpoint no configurado, Admin API no accesible, etc.) -- nunca se
    inventa un valor."""
    total_bytes: Optional[int] = None
    used_bytes: Optional[int] = None
    free_bytes: Optional[int] = None
