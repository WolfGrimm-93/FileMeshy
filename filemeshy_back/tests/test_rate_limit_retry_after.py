"""Ronda 12b -- el 429 de los rate-limits de shares (públicos y dirigidos) trae
`Retry-After` (segundos restantes), no solo el texto "Intenta en N segundos"."""
import io
import uuid

import pytest

from app.auth.service import retry_after_seconds, too_many_requests

from conftest import auth_headers, grant_permission, login_user, register_user


@pytest.mark.parametrize("message, expected", [
    ("Demasiadas solicitudes. Intenta en 42 segundos", 42),
    ("Demasiados intentos. Intenta en 5 minutos", 300),
    ("Demasiados intentos. Intenta en 2 horas", 7200),
    ("mensaje sin tiempo", 60),
])
def test_retry_after_seconds_parses_limiter_messages(message, expected):
    assert retry_after_seconds(message) == expected
    exc = too_many_requests(message)
    assert exc.status_code == 429 and exc.headers == {"Retry-After": str(expected)}


def test_public_share_429_has_retry_after_header(client):
    from app.files.router import PUBLIC_SHARE_RATE_LIMIT_MAX_REQUESTS

    last = None
    for _ in range(PUBLIC_SHARE_RATE_LIMIT_MAX_REQUESTS + 5):
        last = client.get(f"/public/shares/{uuid.uuid4().hex}")
        if last.status_code == 429:
            break
    assert last.status_code == 429, last.status_code
    retry = last.headers.get("retry-after")
    assert retry and retry.isdigit() and 1 <= int(retry) <= 3600
    assert "Intenta en" in last.text


def test_directed_share_429_has_retry_after_header(client, db_session):
    creds_a = register_user(client)
    grant_permission(db_session, creds_a["email"], "shares.create")
    token_a = login_user(client, creds_a["email"], creds_a["password"]).json()["data"]["access_token"]
    creds_b = register_user(client)
    token_b = login_user(client, creds_b["email"], creds_b["password"]).json()["data"]["access_token"]
    f = client.post("/files/upload", headers=auth_headers(token_a),
                    files={"file": ("r.txt", io.BytesIO(b"x"), "text/plain")}).json()
    share = client.post(f"/files/{f['id']}/shares", headers=auth_headers(token_a),
                        json={"shared_with_email": creds_b["email"]}).json()
    last = None
    for _ in range(80):
        last = client.get(f"/shares/{share['id']}", headers=auth_headers(token_b))
        if last.status_code == 429:
            break
    assert last.status_code == 429, last.status_code
    retry = last.headers.get("retry-after")
    assert retry and retry.isdigit() and 1 <= int(retry) <= 3600
