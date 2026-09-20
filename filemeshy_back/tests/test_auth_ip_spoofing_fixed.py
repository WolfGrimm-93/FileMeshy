"""Confirma el FIX del bypass de rate-limit/CAPTCHA por IP spoofeada en
`POST /auth/register` (reemplaza a `test_rate_limit_ip_spoofing.py`, que
documentaba el bug con `xfail(strict=True)` -- con el fix aplicado, ese test
habría pasado a XPASS inesperado y roto el suite).

Causa raíz (ver `app/auth/router.py::_get_real_ip`): antes, el header
X-Real-IP se confiaba SIEMPRE, sin validar que la request viniera de un
proxy real -- rotarlo en cada request abría un cupo de rate-limit nuevo por
"IP" declarada. El fix agrega `settings.TRUSTED_PROXY_IPS`
(app/core/config.py): X-Real-IP/CF-Connecting-IP solo se usan si
`request.client.host` (la IP de la conexión TCP real, no falsificable) está
en esa lista. En este stack de test la lista está vacía, así que el header
se ignora por completo y siempre se usa la IP real.
"""
from conftest import DEFAULT_PASSWORD, unique_email

# Con 12 intentos alcanza para cruzar el límite real (8/hora) con margen.
ATTEMPTS = 12


def test_register_rate_limit_cannot_be_bypassed_by_rotating_x_real_ip(client):
    statuses = []
    for i in range(ATTEMPTS):
        fake_ip = f"203.0.113.{i}"  # TEST-NET-3 (RFC 5737) -- nunca es local
        resp = client.post(
            "/auth/register",
            headers={"X-Real-IP": fake_ip},
            json={
                "email": unique_email(),
                "first_name": "Pytest",
                "last_name": "Spoof",
                "password": DEFAULT_PASSWORD,
            },
        )
        statuses.append(resp.status_code)

    # Comportamiento correcto: en algún punto el backend bloquea con 429 pese
    # a que cada request declara una IP "nueva" -- el límite se basa en la
    # conexión real (127.0.0.1 dentro del contenedor de test), no en un
    # header que controla libremente quien llama.
    assert 429 in statuses, (
        f"Se esperaba al menos un 429 entre {ATTEMPTS} registros rotando "
        f"X-Real-IP, pero todas las respuestas fueron: {statuses} -- el "
        "bypass de IP spoofing seguiría existiendo."
    )

    # Y las respuestas ANTES de tocar el límite deben haber sido éxitos
    # reales (201) -- si todas fueran 429 desde el principio, no estaríamos
    # probando nada (podría ser un bucket sucio de otro test).
    assert 201 in statuses, f"Ningún registro tuvo éxito antes del límite: {statuses}"
