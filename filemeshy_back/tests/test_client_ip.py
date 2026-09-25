"""Tests de `get_real_ip` (app/shared/utils/client_ip.py) y del rate-limit
por IP real de los shares públicos.

Unitarios in-process (Request falso + monkeypatch de settings) y un E2E
estilo test_auth_ip_spoofing_fixed.py.
"""
import pytest
from starlette.requests import Request

from app.core.config import Settings, settings
from app.shared.utils.client_ip import get_real_ip, parse_trusted_proxies, rate_limit_ip_key


def make_request(client_host, headers=None):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {"type": "http", "method": "GET", "path": "/", "headers": raw,
             "client": (client_host, 1234) if client_host else None}
    return Request(scope)


@pytest.fixture
def trusted(monkeypatch):
    def _set(entries):
        monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", entries)
    return _set


def test_untrusted_connection_ignores_headers(trusted):
    trusted(["172.18.0.5"])
    req = make_request("203.0.113.9", {"X-Real-IP": "1.2.3.4", "CF-Connecting-IP": "5.6.7.8"})
    assert get_real_ip(req) == "203.0.113.9"


def test_empty_list_ignores_headers(trusted):
    trusted([])
    req = make_request("172.18.0.5", {"X-Real-IP": "1.2.3.4"})
    assert get_real_ip(req) == "172.18.0.5"


def test_trusted_single_ip_uses_header(trusted):
    trusted(["172.18.0.5"])
    assert get_real_ip(make_request("172.18.0.5", {"X-Real-IP": "1.2.3.4"})) == "1.2.3.4"


def test_trusted_cidr_uses_x_real_ip_and_ignores_cf_by_default(trusted):
    trusted(["172.18.0.0/16"])
    req = make_request("172.18.7.9", {"X-Real-IP": "1.2.3.4", "CF-Connecting-IP": "5.6.7.8"})
    assert get_real_ip(req) == "1.2.3.4"
    # Solo cf-connecting-ip enviado por un cliente tras un proxy de confianza
    # (nginx no lo pisa): se IGNORA con el default.
    assert get_real_ip(make_request("172.18.7.9", {"CF-Connecting-IP": "5.6.7.8"})) == "172.18.7.9"
    # Fuera del CIDR: se ignora todo.
    assert get_real_ip(make_request("172.19.0.1", {"X-Real-IP": "1.2.3.4"})) == "172.19.0.1"


def test_cf_connecting_ip_is_opt_in_with_configured_order(trusted, monkeypatch):
    trusted(["172.18.0.0/16"])
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IP_HEADERS", ["cf-connecting-ip", "x-real-ip"])
    req = make_request("172.18.7.9", {"X-Real-IP": "1.2.3.4", "CF-Connecting-IP": "5.6.7.8"})
    assert get_real_ip(req) == "5.6.7.8"
    # Header inválido: pasa al siguiente válido.
    req = make_request("172.18.0.2", {"CF-Connecting-IP": "basura", "X-Real-IP": "9.9.9.9"})
    assert get_real_ip(req) == "9.9.9.9"
    # Fuera de la lista de confianza: se ignoran incluso los opt-in.
    assert get_real_ip(make_request("203.0.113.9", {"CF-Connecting-IP": "5.6.7.8"})) == "203.0.113.9"


def test_invalid_header_falls_back_to_direct_ip(trusted):
    trusted(["172.18.0.0/16"])
    assert get_real_ip(make_request("172.18.0.2", {"X-Real-IP": "no-es-una-ip"})) == "172.18.0.2"


def test_ipv6_with_zone_id_is_rejected(trusted):
    trusted(["172.18.0.0/16"])
    assert get_real_ip(make_request("172.18.0.2", {"X-Real-IP": "fe80::1%eth0"})) == "172.18.0.2"
    assert get_real_ip(make_request("172.18.0.2", {"X-Real-IP": "fe80::1%1"})) == "172.18.0.2"


def test_headers_setting_is_validated_and_normalized():
    ok = Settings(TRUSTED_PROXY_IP_HEADERS=["CF-Connecting-IP", " X-Real-IP "])
    assert ok.TRUSTED_PROXY_IP_HEADERS == ["cf-connecting-ip", "x-real-ip"]
    assert Settings().TRUSTED_PROXY_IP_HEADERS == ["x-real-ip"]
    with pytest.raises(Exception, match="x-forwarded-for"):
        Settings(TRUSTED_PROXY_IP_HEADERS=["x-forwarded-for"])


def test_prefix_zero_is_rejected():
    for bad in ("0.0.0.0/0", "::/0"):
        with pytest.raises(ValueError, match=r"/0"):
            parse_trusted_proxies([bad])
        with pytest.raises(Exception, match=r"/0"):
            Settings(TRUSTED_PROXY_IPS=[bad])


def test_rate_limit_key_groups_ipv6_by_64():
    assert rate_limit_ip_key("203.0.113.5") == "203.0.113.5"
    a = rate_limit_ip_key("2001:db8:1:2::1")
    b = rate_limit_ip_key("2001:db8:1:2:ffff:ffff:ffff:ffff")
    assert a == b == "2001:db8:1:2::/64"
    assert rate_limit_ip_key("2001:db8:1:3::1") != a
    assert rate_limit_ip_key("unknown") == "unknown"


def test_ipv4_mapped_is_normalized(trusted):
    trusted(["172.18.0.0/16"])
    # Conexión directa mapeada cuenta como IPv4 para la lista de confianza.
    req = make_request("::ffff:172.18.0.3", {"X-Real-IP": "::ffff:1.2.3.4"})
    assert get_real_ip(req) == "1.2.3.4"
    trusted([])
    assert get_real_ip(make_request("::ffff:10.0.0.1")) == "10.0.0.1"


def test_unparseable_direct_ip_returns_it_without_headers(trusted):
    trusted(["172.18.0.0/16"])
    assert get_real_ip(make_request("unknown", {"X-Real-IP": "1.2.3.4"})) == "unknown"
    assert get_real_ip(make_request(None, {"X-Real-IP": "1.2.3.4"})) == "unknown"


def test_invalid_trusted_entry_is_rejected_at_startup():
    with pytest.raises(ValueError, match="TRUSTED_PROXY_IPS.*no-es-cidr"):
        parse_trusted_proxies(["172.18.0.0/16", "no-es-cidr"])
    with pytest.raises(Exception, match="TRUSTED_PROXY_IPS.*basura"):
        Settings(TRUSTED_PROXY_IPS=["basura"])


def test_public_share_rate_limit_cannot_be_bypassed_by_rotating_x_real_ip(client):
    """E2E: rotar X-Real-IP (lista vacía en este stack) no evade el 429."""
    statuses = []
    for i in range(35):
        resp = client.get(
            "/public/shares/token-inexistente-pytest",
            headers={"X-Real-IP": f"203.0.113.{i}"},
        )
        statuses.append(resp.status_code)
    assert 429 in statuses, f"Sin 429 rotando X-Real-IP: {statuses}"
