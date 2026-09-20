"""Confirma que `GET /storage-quotas/me` devuelve SOLO la cuota del usuario
autenticado -- nunca la de otro. El endpoint no acepta ningún `user_id`
como parámetro (a diferencia de `PUT /storage-quotas/{user_id}`, que sí
requiere permiso admin): siempre lee `current_user.id`, así que no hay forma
de pedir la cuota ajena por acá (ver
app/storage_quota/router.py::get_my_storage_quota).

Usa el admin funcional del stack (`audit-admin@example.com`) para asignarle
un límite puntual a un usuario y confirmar que ESE límite nunca se filtra
al `/me` de otro usuario distinto.
"""
from conftest import auth_headers, login_user, register_user

ADMIN_EMAIL = "audit-admin@example.com"
ADMIN_PASSWORD = "AuditTest123!@#"


def test_storage_quota_me_returns_only_own_quota(client):
    creds_a = register_user(client)
    user_a_id = creds_a["user"]["id"]
    token_a = login_user(client, creds_a["email"], creds_a["password"]).json()["data"]["access_token"]

    creds_b = register_user(client)
    token_b = login_user(client, creds_b["email"], creds_b["password"]).json()["data"]["access_token"]

    # Usuario recién registrado, sin límite configurado todavía.
    resp_a_before = client.get("/storage-quotas/me", headers=auth_headers(token_a))
    assert resp_a_before.status_code == 200, resp_a_before.text
    assert resp_a_before.json()["limit_bytes"] is None
    assert resp_a_before.json()["bytes_used"] == 0

    # El admin le asigna un límite puntual a A.
    admin_login = login_user(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert admin_login.status_code == 200, admin_login.text
    admin_token = admin_login.json()["data"]["access_token"]

    limit_for_a = 123456789
    update_resp = client.put(
        f"/storage-quotas/{user_a_id}",
        headers=auth_headers(admin_token),
        json={"limit_bytes": limit_for_a},
    )
    assert update_resp.status_code == 200, update_resp.text

    # A ahora ve SU límite nuevo...
    resp_a_after = client.get("/storage-quotas/me", headers=auth_headers(token_a))
    assert resp_a_after.status_code == 200, resp_a_after.text
    assert resp_a_after.json()["limit_bytes"] == limit_for_a

    # ...pero B sigue viendo la SUYA (sin límite) -- el límite de A nunca se
    # filtra al /me de otro usuario.
    resp_b = client.get("/storage-quotas/me", headers=auth_headers(token_b))
    assert resp_b.status_code == 200, resp_b.text
    assert resp_b.json()["limit_bytes"] is None
    assert resp_b.json()["bytes_used"] == 0


def test_storage_quota_me_requires_authentication(client):
    resp = client.get("/storage-quotas/me")
    assert resp.status_code in (401, 403)
