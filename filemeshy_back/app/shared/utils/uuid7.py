"""Helper para generar UUID v7 (ordenables por tiempo), norma del proyecto.

uuid_utils.uuid7() devuelve su propio tipo (no uuid.UUID de la stdlib), por eso
se convierte explícitamente vía los bytes crudos. Reusable para cualquier PK
nueva del proyecto (ej: tenants) y para migraciones de UUID v4 -> v7 futuras.
"""
import uuid

import uuid_utils


def uuid7() -> uuid.UUID:
    """Genera un UUID v7 como uuid.UUID estándar de la stdlib."""
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)
