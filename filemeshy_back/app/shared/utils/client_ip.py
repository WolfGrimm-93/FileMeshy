"""Resolución de la IP real del cliente, compartida por auth, platform,
shares públicos y auditoría.

Vive en un módulo neutral (no en app/auth/router.py) para que ningún módulo
de negocio tenga que importar el router de auth solo por esta utilidad.
"""
import ipaddress
from functools import lru_cache
from typing import Optional, Tuple

from fastapi import Request


def parse_trusted_proxies(entries) -> Tuple:
    """Parsea la lista de proxies de confianza (IPs sueltas o CIDR) a redes.

    Una IP suelta se convierte en /32 (IPv4) o /128 (IPv6). Una entrada
    inválida lanza ValueError con un mensaje claro (se usa como validator
    de settings, así el error aparece al arrancar)."""
    networks = []
    for raw in entries or []:
        text = str(raw).strip()
        if not text:
            continue
        try:
            network = ipaddress.ip_network(text, strict=False)
        except ValueError as exc:
            raise ValueError(
                f"TRUSTED_PROXY_IPS contiene una entrada inválida: '{text}' "
                "(se espera una IP o un CIDR, ej. 172.18.0.5 o 172.18.0.0/16)"
            ) from exc
        if network.prefixlen == 0:
            # 0.0.0.0/0 o ::/0 confiaría en TODO el mundo (cualquier cliente
            # podría falsificar los headers).
            raise ValueError(
                f"TRUSTED_PROXY_IPS contiene una entrada inválida: '{text}' "
                "(prefijo /0 no permitido: confiaría en cualquier cliente)"
            )
        networks.append(network)
    return tuple(networks)


@lru_cache(maxsize=32)
def _parsed_cached(entries: Tuple[str, ...]) -> Tuple:
    return parse_trusted_proxies(list(entries))


def _normalize_ip(value: str) -> Optional[str]:
    """Devuelve la IP normalizada (IPv4-mapped -> IPv4) o None si no parsea."""
    candidate = value.strip()
    # IPv6 con zona/scope (fe80::1%eth0) no es una IP de cliente válida.
    if "%" in candidate:
        return None
    try:
        addr = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return str(addr)


def _is_trusted(ip: str) -> bool:
    # Import diferido: config.py usa este módulo desde su validator.
    from app.core.config import settings

    addr = ipaddress.ip_address(ip)
    networks = _parsed_cached(tuple(settings.TRUSTED_PROXY_IPS))
    return any(addr.version == net.version and addr in net for net in networks)


def get_real_ip(request: Request) -> str:
    """Obtiene la IP real del cliente.

    `direct_ip` (request.client.host) es la IP de la conexión TCP real -- la
    única que ningún cliente puede falsificar. Los headers CF-Connecting-IP
    (Cloudflare) y X-Real-IP (nginx) SOLO se confían si `direct_ip` está en
    `settings.TRUSTED_PROXY_IPS` (IPs o CIDR). Si no está (o no parsea), se
    devuelve la IP directa SIN mirar ningún header. Solo se leen los headers
    de `settings.TRUSTED_PROXY_IP_HEADERS` (default solo x-real-ip), en ese
    orden. El valor del header se valida con ip_address(); si es inválido
    (incluida zona IPv6 con '%') se usa la IP directa.
    """
    from app.core.config import settings

    raw_direct = request.client.host if request.client else "unknown"
    direct_ip = _normalize_ip(raw_direct)
    if direct_ip is None:
        return raw_direct
    if not _is_trusted(direct_ip):
        return direct_ip
    for header in settings.TRUSTED_PROXY_IP_HEADERS:
        value = request.headers.get(header)
        if value:
            candidate = _normalize_ip(value)
            if candidate is not None:
                return candidate
    return direct_ip


def rate_limit_ip_key(ip: str) -> str:
    """IP normalizada para usar como clave de rate-limit: IPv4 sin cambio;
    IPv6 se agrupa por /64 (un cliente controla todo su /64, si no rotar
    dentro del prefijo evadiría el límite). Valores no-IP se devuelven tal
    cual (ej. 'unknown')."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if isinstance(addr, ipaddress.IPv6Address):
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return ip
