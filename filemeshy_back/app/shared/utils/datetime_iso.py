"""Formato ISO 8601 de fechas para respuestas JSON.

Ronda 12b: varios endpoints armaban `dt.isoformat() + 'Z'`; con un datetime
tz-aware (columnas `DateTime(timezone=True)`) eso da `...+00:00Z`, que NO es ISO
8601 válido (`new Date()` en JS devuelve Invalid Date -> columna Fecha/Hora vacía en
los logs de auditoría). Este helper es el único lugar que decide el sufijo."""
from datetime import date, datetime, timezone
from typing import Optional, Union


def to_utc_iso(value: Optional[Union[datetime, date]]) -> Optional[str]:
    """`datetime` -> ISO 8601 en UTC con sufijo `Z` (p. ej. 2026-09-26T14:47:41.115218Z).
    Un datetime sin tz se interpreta como UTC (así se guardan/generan en este
    proyecto: `datetime.utcnow()`, `func.now()` en servidores UTC). `None` -> None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value.isoformat()
