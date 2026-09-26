"""Ronda 12 (B1) -- `_parse_user_agent` (app/auth/schemas.py), funcion pura.

Bugs que atrapan estos casos: iPhone/iPad reportados como "Safari en macOS"
(el UA trae "like Mac OS X"), Opera (OPR/) como Chrome, Chrome iOS (CriOS)
como Safari, Chromium sin "chrome" como Safari, y clientes no navegador
(curl, httpx, "unknown", vacio) como "Navegador desconocido en SO
desconocido"."""
import pytest

from app.auth.schemas import _parse_user_agent

CHROME_LINUX_HEADLESS = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "HeadlessChrome/131.0.0.0 Safari/537.36"
)
CHROME_WIN = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
EDGE_WIN = CHROME_WIN + " Edg/131.0.0.0"
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0"
SAFARI_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.1 Safari/605.1.15"
)
SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
)
SAFARI_IPAD = SAFARI_IPHONE.replace("iPhone; CPU iPhone OS", "iPad; CPU OS")
CRIOS = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) CriOS/120.0.6099.119 Mobile/15E148 Safari/604.1"
)
OPERA_WIN = CHROME_WIN + " OPR/106.0.0.0"
ANDROID_CHROME = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Mobile Safari/537.36"
)
CHROMIUM_LINUX = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chromium/120.0.0.0 Safari/537.36"
)


@pytest.mark.parametrize(
    "ua, expected",
    [
        (CHROME_LINUX_HEADLESS, ("desktop", "Chrome en Linux")),
        (CHROME_WIN, ("desktop", "Chrome en Windows 10/11")),
        (EDGE_WIN, ("desktop", "Edge en Windows 10/11")),
        (FIREFOX_LINUX, ("desktop", "Firefox en Linux")),
        (SAFARI_MAC, ("desktop", "Safari en macOS")),
        (SAFARI_IPHONE, ("mobile", "Safari en iOS")),
        (SAFARI_IPAD, ("mobile", "Safari en iOS")),
        (CRIOS, ("mobile", "Chrome en iOS")),
        (OPERA_WIN, ("desktop", "Opera en Windows 10/11")),
        (ANDROID_CHROME, ("mobile", "Chrome en Android")),
        (CHROMIUM_LINUX, ("desktop", "Chromium en Linux")),
        ("curl/8.5.0", ("desktop", "Cliente API")),
        ("python-httpx/0.25.2", ("desktop", "Cliente API")),
        ("python-requests/2.31.0", ("desktop", "Cliente API")),
        ("PostmanRuntime/7.36.0", ("desktop", "Cliente API")),
        ("okhttp/4.12.0", ("desktop", "Cliente API")),
        ("unknown", ("desktop", "Cliente API")),
        ("", ("desktop", "Cliente API")),
        (None, ("desktop", "Cliente API")),
    ],
)
def test_parse_user_agent(ua, expected):
    assert _parse_user_agent(ua) == expected
