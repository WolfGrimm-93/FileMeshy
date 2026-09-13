"""Utilidades de precision monetaria para FileMeshy."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def round_money(value: Any, decimals: int = 2) -> float:
    """Redondea un valor monetario a la precision indicada usando ROUND_HALF_UP.

    Evita el problema clasico de punto flotante:
        >>> 0.1 + 0.2  # 0.30000000000000004
        >>> round_money(0.1 + 0.2)  # 0.3

    Retorna float (no Decimal) para compatibilidad con JSON/Pydantic.
    """
    if value is None:
        return 0.0
    try:
        d = Decimal(str(value))
        if d.is_nan() or d.is_infinite():
            return 0.0
        quantize_str = "0." + "0" * decimals
        return float(d.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP))
    except Exception:
        return 0.0
