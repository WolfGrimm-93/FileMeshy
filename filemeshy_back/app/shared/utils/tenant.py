"""Utilidades de tenant para estructura de almacenamiento multi-empresa."""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Cacheado por schema de tenant (tenant_schema_ctx.get(), None en modo local)
# en vez de un unico string global -- con un solo valor global, en modo cloud
# el primer tenant que llamaba get_company_code() dejaba su slug cacheado
# para siempre, y el resto de los tenants recibian ese mismo slug (archivos
# de otro tenant terminando bajo el prefijo de MinIO equivocado).
_cached_code: dict[Optional[str], str] = {}


def _slugify(text: str) -> str:
    """Convierte un texto en un slug seguro para usar como ruta en MinIO."""
    text = text.lower().strip()
    text = re.sub(r"[áàäâ]", "a", text)
    text = re.sub(r"[éèëê]", "e", text)
    text = re.sub(r"[íìïî]", "i", text)
    text = re.sub(r"[óòöô]", "o", text)
    text = re.sub(r"[úùüû]", "u", text)
    text = re.sub(r"[ñ]", "n", text)
    text = re.sub(r"[^a-z0-9_-]", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-") or "default"


def get_company_code(db) -> str:
    """Retorna el identificador de la empresa para usar como prefijo en MinIO.

    Prioridad:
      1. TENANT_SLUG del .env (override manual — útil en modo cloud)
      2. "default" si no hay nada configurado

    Se cachea en memoria por schema de tenant activo (todo bajo la misma
    clave en modo local) — llamar invalidate_company_code_cache() si el
    TENANT_SLUG cambia.
    """
    from app.core.database import tenant_schema_ctx
    tenant_key = tenant_schema_ctx.get()

    if tenant_key in _cached_code:
        return _cached_code[tenant_key]

    # 1. Override desde variable de entorno (modo cloud / instalador)
    from app.core.config import settings as _s
    env_slug = getattr(_s, "TENANT_SLUG", None)
    if env_slug:
        _cached_code[tenant_key] = _slugify(env_slug)
        logger.info(f"[Tenant] Slug desde TENANT_SLUG env: {_cached_code[tenant_key]}")
        return _cached_code[tenant_key]

    # 2. Fallback final
    _cached_code[tenant_key] = "default"
    logger.warning("[Tenant] Usando slug fallback: default")
    return _cached_code[tenant_key]


def invalidate_company_code_cache() -> None:
    """Limpia el cache del company_code del tenant activo (llamar si la empresa cambia su código)."""
    from app.core.database import tenant_schema_ctx
    _cached_code.pop(tenant_schema_ctx.get(), None)
