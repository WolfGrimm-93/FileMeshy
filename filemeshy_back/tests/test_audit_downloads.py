"""Auditoría explícita de descargas (`log_audit`, action DOWNLOAD sobre
`files`): descarga propia, vía share dirigido y vía link público. Los
listados, previews y los 404/403 NO generan fila."""
import io

from conftest import auth_headers, grant_permission, login_user, register_user


def _user(client, db_session, permissions=()):
    creds = register_user(client)
    for perm in permissions:
        grant_permission(db_session, creds["email"], perm)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    return creds, token


def _upload(client, token):
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": ("pytest_audit_dl.txt", io.BytesIO(b"hola auditoria"), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _rows(db_session, file_id):
    from app.audit.models import AuditLog

    db_session.rollback()
    return (
        db_session.query(AuditLog)
        .filter(AuditLog.table_name == "files", AuditLog.record_id == file_id, AuditLog.action == "DOWNLOAD")
        .all()
    )


def test_own_download_creates_one_download_row(client, db_session):
    creds, token = _user(client, db_session)
    file_id = _upload(client, token)
    assert _rows(db_session, file_id) == []

    # Un listado NO genera fila; el preview tampoco.
    assert client.get("/files", headers=auth_headers(token)).status_code == 200
    client.get(f"/files/{file_id}/preview", headers=auth_headers(token))
    assert _rows(db_session, file_id) == []

    resp = client.get(f"/files/{file_id}/download", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    rows = _rows(db_session, file_id)
    assert len(rows) == 1
    assert rows[0].user_id == creds["user"]["id"]
    assert rows[0].user_email == creds["email"]
    assert rows[0].new_data["via"] == "direct"
    # IP real de la conexión en el stack de test (127.0.0.1); el X-Real-IP
    # que manda el fixture `client` (10.x) se ignora porque TRUSTED_PROXY_IPS
    # está vacío.
    assert rows[0].ip_address == "127.0.0.1"


def test_failed_downloads_do_not_create_rows(client, db_session):
    _, token_a = _user(client, db_session)
    _, token_b = _user(client, db_session)
    file_id = _upload(client, token_a)

    # B (ajeno) -> 404/403, sin fila.
    resp = client.get(f"/files/{file_id}/download", headers=auth_headers(token_b))
    assert resp.status_code in (403, 404)
    # Sin autenticar -> 401.
    assert client.get(f"/files/{file_id}/download").status_code in (401, 403)
    # Share público inexistente.
    assert client.get(f"/public/shares/no-existe-pytest/download/{file_id}").status_code == 404
    assert _rows(db_session, file_id) == []


def test_directed_and_public_share_downloads_are_audited(client, db_session):
    creds_a, token_a = _user(client, db_session, permissions=["shares.create"])
    creds_b, token_b = _user(client, db_session)
    file_id = _upload(client, token_a)

    directed = client.post(
        f"/files/{file_id}/shares", headers=auth_headers(token_a),
        json={"shared_with_email": creds_b["email"]},
    )
    assert directed.status_code == 201, directed.text
    share_id = directed.json()["id"]
    resp = client.get(f"/shares/{share_id}/download/{file_id}", headers=auth_headers(token_b))
    assert resp.status_code == 200, resp.text

    public = client.post(f"/files/{file_id}/shares", headers=auth_headers(token_a), json={})
    assert public.status_code == 201, public.text
    token = public.json()["token"]
    public_share_id = public.json()["id"]
    # Ver el contenido público NO audita; solo la descarga.
    assert client.get(f"/public/shares/{token}").status_code == 200
    assert len(_rows(db_session, file_id)) == 1
    resp = client.get(f"/public/shares/{token}/download/{file_id}")
    assert resp.status_code == 200, resp.text

    rows = {r.new_data["via"]: r for r in _rows(db_session, file_id)}
    assert set(rows) == {"directed_share", "public_share"}
    assert rows["directed_share"].user_id == creds_b["user"]["id"]
    assert rows["directed_share"].new_data["share_id"] == share_id
    assert rows["public_share"].user_id is None
    assert rows["public_share"].user_email is None
    assert rows["public_share"].new_data["share_id"] == public_share_id
    assert rows["public_share"].ip_address == "127.0.0.1"
    assert rows["directed_share"].ip_address == "127.0.0.1"
