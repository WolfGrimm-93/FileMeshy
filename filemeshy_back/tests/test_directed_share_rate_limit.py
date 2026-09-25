"""Rate-limit por usuario en los endpoints autenticados de shares dirigidos:
lecturas 60/min (`directed_share_read:{user.id}`), escrituras 10/min
(`directed_share_write:{user.id}`). El cupo es por usuario: ni el dueño ni un
tercero se ven afectados cuando el destinatario lo agota."""
import io

from conftest import auth_headers, grant_permission, login_user, register_user


def _user(client, db_session, permissions=()):
    creds = register_user(client)
    for perm in permissions:
        grant_permission(db_session, creds["email"], perm)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    return creds, token


def _setup(client, db_session):
    creds_a, token_a = _user(client, db_session, permissions=["shares.create"])
    creds_b, token_b = _user(client, db_session)
    _, token_c = _user(client, db_session)
    up = client.post(
        "/files/upload",
        headers=auth_headers(token_a),
        files={"file": ("pytest_rl_share.txt", io.BytesIO(b"hola"), "text/plain")},
    )
    assert up.status_code == 201, up.text
    file_id = up.json()["id"]
    sh = client.post(
        f"/files/{file_id}/shares",
        headers=auth_headers(token_a),
        json={"shared_with_email": creds_b["email"]},  # permission view
    )
    assert sh.status_code == 201, sh.text
    return sh.json()["id"], file_id, token_a, token_b, token_c


def test_directed_share_reads_are_rate_limited_per_user(client, db_session):
    share_id, file_id, token_a, token_b, token_c = _setup(client, db_session)

    statuses = []
    for i in range(65):
        path = f"/shares/{share_id}" if i % 2 == 0 else f"/shares/{share_id}/download/{file_id}"
        statuses.append(client.get(path, headers=auth_headers(token_b)).status_code)
    assert 429 in statuses, statuses
    assert statuses[0] == 200

    # El dueño y un tercero tienen su propio cupo.
    assert client.get(f"/shares/{share_id}", headers=auth_headers(token_a)).status_code == 200
    assert client.get(f"/shares/{share_id}", headers=auth_headers(token_c)).status_code == 404


def test_directed_share_writes_are_rate_limited_per_user(client, db_session):
    share_id, _, token_a, token_b, token_c = _setup(client, db_session)

    statuses = []
    for i in range(34):
        files = {"file": ("x.txt", io.BytesIO(b"x"), "text/plain")}
        if i % 2 == 0:
            r = client.post(f"/shares/{share_id}/files", headers=auth_headers(token_b), files=files)
        else:
            r = client.put(f"/shares/{share_id}/content", headers=auth_headers(token_b), files=files)
        statuses.append(r.status_code)
    # Share 'view': antes del límite responde 403, luego 429.
    assert statuses[0] == 403, statuses
    assert 429 in statuses, statuses

    files = {"file": ("x.txt", io.BytesIO(b"x"), "text/plain")}
    r = client.put(f"/shares/{share_id}/content", headers=auth_headers(token_c), files=files)
    assert r.status_code == 404, r.text  # tercero: no afectado por el cupo de B
    files = {"file": ("x.txt", io.BytesIO(b"x"), "text/plain")}
    r = client.put(f"/shares/{share_id}/content", headers=auth_headers(token_a), files=files)
    assert r.status_code == 403, r.text  # dueño: no 429 (share 'view')
