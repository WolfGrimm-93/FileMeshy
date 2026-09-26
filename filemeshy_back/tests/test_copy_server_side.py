"""Ronda 12d -- la copia de archivos/carpetas es SERVER-SIDE (S3 CopyObject): el contenido
nunca se lee a memoria del backend (con archivos de 10-20 GB, `_read_private_object` era un OOM).
La copia conserva cuota, versión inicial, `scan_status` y se re-indexa."""
import hashlib
import io

from sqlalchemy import text

from conftest import auth_headers, grant_permission, login_user, register_user


def _setup(client, db_session, content=b"contenido para copiar " * 50):
    creds = register_user(client)
    grant_permission(db_session, creds["email"], "folders.create")
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    h = auth_headers(token)
    f = client.post("/files/upload", headers=h, files={"file": ("orig.txt", io.BytesIO(content), "text/plain")})
    assert f.status_code == 201, f.text
    return creds["email"], h, f.json()


def _user(db_session, email):
    import app.worker.celery_app  # noqa: F401

    from app.users.repository import user as crud_user

    return crud_user.get_by_email(db_session, email)


def _sha(storage_key):
    from app.core.config import settings
    from app.files.service import _get_client

    body = _get_client().get_object(Bucket=settings.MINIO_PRIVATE_BUCKET, Key=storage_key)["Body"].read()
    return hashlib.sha256(body).hexdigest()


def _forbid_full_read(monkeypatch):
    from app.files import router as files_router

    def boom(*a, **k):
        raise AssertionError("la copia NO debe leer el objeto completo a memoria")

    monkeypatch.setattr(files_router, "_read_private_object", boom)
    return files_router


def test_file_copy_never_reads_object_into_memory_and_keeps_everything(client, db_session, monkeypatch):
    email, h, orig = _setup(client, db_session)
    files_router = _forbid_full_read(monkeypatch)
    enqueued = []
    monkeypatch.setattr(files_router, "_enqueue_content_indexing", lambda fid: enqueued.append(fid))
    user = _user(db_session, email)
    quota_before = db_session.execute(text("SELECT coalesce(max(bytes_used),0) FROM user_storage_quotas WHERE user_id=:u"), {"u": user.id}).scalar_one()

    copy = files_router.copy_file(file_id=__import__("uuid").UUID(orig["id"]), payload=None, db=db_session, current_user=user)

    keys = dict(db_session.execute(text("SELECT id::text, storage_key FROM files WHERE id IN (:a, :b)"),
                                   {"a": orig["id"], "b": str(copy.id)}).all())
    assert keys[orig["id"]] != keys[str(copy.id)]
    assert _sha(keys[orig["id"]]) == _sha(keys[str(copy.id)])  # mismo contenido (sha256)
    assert copy.size_bytes == orig["size_bytes"] and copy.mime_type == orig["mime_type"]
    assert copy.scan_status == "clean" and copy.name.endswith("(copia)")
    versions = db_session.execute(text("SELECT count(*), min(version_number) FROM file_versions WHERE file_id=:f"), {"f": copy.id}).first()
    assert tuple(versions) == (1, 1)
    quota_after = db_session.execute(text("SELECT coalesce(max(bytes_used),0) FROM user_storage_quotas WHERE user_id=:u"), {"u": user.id}).scalar_one()
    assert quota_after - quota_before == orig["size_bytes"]
    assert enqueued == [copy.id]  # la copia se re-indexa


def test_folder_copy_is_server_side_and_reindexes_every_file(client, db_session, monkeypatch):
    email, h, orig = _setup(client, db_session)
    fid = client.post("/folders", headers=h, json={"name": "carpeta"}).json()["id"]
    for i in range(2):
        r = client.post("/files/upload", headers=h, data={"folder_id": fid},
                        files={"file": (f"f{i}.txt", io.BytesIO(b"dato %d" % i * 30), "text/plain")})
        assert r.status_code == 201
    files_router = _forbid_full_read(monkeypatch)
    enqueued = []
    monkeypatch.setattr(files_router, "_enqueue_content_indexing", lambda x: enqueued.append(x))
    user = _user(db_session, email)
    new_folder = files_router.copy_folder(folder_id=__import__("uuid").UUID(fid), payload=None, db=db_session, current_user=user)
    assert new_folder.id is not None
    assert len(enqueued) == 2


def test_copy_of_non_clean_file_is_refused_and_never_becomes_clean(client, db_session, monkeypatch):
    import pytest
    from fastapi import HTTPException

    email, h, orig = _setup(client, db_session)
    files_router = _forbid_full_read(monkeypatch)
    db_session.execute(text("UPDATE files SET scan_status='pending' WHERE id=:f"), {"f": orig["id"]})
    db_session.commit()
    user = _user(db_session, email)
    before = db_session.execute(text("SELECT count(*) FROM files WHERE owner_id=:u"), {"u": user.id}).scalar_one()
    with pytest.raises(HTTPException) as exc:
        files_router.copy_file(file_id=__import__("uuid").UUID(orig["id"]), payload=None, db=db_session, current_user=user)
    assert exc.value.status_code in (404, 409)
    db_session.expire_all()
    assert db_session.execute(text("SELECT count(*) FROM files WHERE owner_id=:u"), {"u": user.id}).scalar_one() == before
    db_session.execute(text("UPDATE files SET scan_status='clean' WHERE id=:f"), {"f": orig["id"]})
    db_session.commit()
