"""Ronda 9 -- coordinación de subida multipart, sesiones de upload, cuota.

Contra el stack real (Postgres, Redis y MinIO reales, sin mocks), mismo
criterio que el resto del suite. Dos formas de ejercitar el flujo acá:

1. Llamando a `app.uploads.service.*` DIRECTO (sin pasar por HTTP) para los
   tests que necesitan subir bytes REALES a una URL presignada -- el
   endpoint público real (`settings.PUBLIC_STORAGE_PROXY_URL`, el proxy
   nginx que el agente de infra de esta misma ronda construye en paralelo)
   apunta a un host (`localhost:58100`) que NO es alcanzable desde DENTRO de
   este contenedor `backend` (es el puerto publicado del contenedor
   `frontend`, otra red/namespace). El fixture `presign_via_internal_minio`
   redirige la FIRMA (no la lógica) al endpoint interno real de MinIO
   (`http://minio:9000`, alcanzable acá, misma red docker) -- valida que la
   firma SigV4 que genera `app/uploads/service.py` es válida de punta a
   punta contra MinIO real (la pieza más riesgosa de todo el diseño). Lo
   que ESTO no puede probar por sí solo es el reenvío transparente de nginx
   en `{PUBLIC_STORAGE_PROXY_URL}` -- eso depende del trabajo en paralelo
   del otro agente, ver el reporte final de esta ronda para el estado de esa
   verificación específica.

2. Vía HTTP real (`client` fixture) para los tests que solo necesitan
   confirmar validación/ownership/status codes, sin subir bytes.
"""
from __future__ import annotations

import os

import httpx
import pytest

from app.core.config import settings
from app.files.repository import file_repo
from app.storage_quota.repository import user_storage_quota_repo
from app.uploads.schemas import (
    CompletedPartIn,
    UploadCompleteRequest,
    UploadInitiateRequest,
)
from app.uploads.service import (
    abort_upload,
    complete_upload,
    initiate_upload,
    refresh_part_urls,
)

from conftest import auth_headers, login_user, register_user

import app.uploads.service as uploads_service


def _get_orm_user(db_session, email: str):
    from app.users.repository import user as crud_user

    user = crud_user.get_by_email(db_session, email)
    assert user is not None, f"Usuario {email} no encontrado tras registrarse"
    return user


@pytest.fixture
def presign_via_internal_minio(monkeypatch):
    """Ver docstring del módulo -- fuerza el cliente de FIRMA de partes a
    apuntar al endpoint interno real de MinIO en vez del proxy público, para
    que el PROPIO proceso de pytest (corriendo dentro del contenedor
    `backend`) pueda hacer el PUT real de cada parte. Resetea el cliente
    cacheado (`app.uploads.service._presign_client*`) antes y después --
    esos globals cachean el primer cliente inicializado por proceso, y si
    algún otro test/request ya lo inicializó con el valor real de
    `PUBLIC_STORAGE_PROXY_URL` antes que este test corra, el patch de
    `settings` solo no alcanzaría."""
    monkeypatch.setattr(settings, "PUBLIC_STORAGE_PROXY_URL", "http://minio:9000")
    uploads_service._presign_client = None
    uploads_service._presign_client_ok = False
    yield
    uploads_service._presign_client = None
    uploads_service._presign_client_ok = False


def _put_part(url: str, data: bytes) -> str:
    with httpx.Client(timeout=30.0) as raw:
        resp = raw.put(url, content=data)
        assert resp.status_code == 200, f"PUT de parte falló: {resp.status_code} {resp.text}"
        etag = resp.headers.get("ETag")
        assert etag, "MinIO no devolvió ETag tras subir la parte"
        return etag


# ---------------------------------------------------------------------------
# Validación de tamaño -- vía HTTP real, settings reales del contenedor
# (MAX_UPLOAD_SIZE_MB=100 / MAX_LARGE_UPLOAD_SIZE_MB=20480 por defecto).
# ---------------------------------------------------------------------------

def test_initiate_rejects_file_within_normal_upload_limit(client):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]

    resp = client.post(
        "/uploads/initiate",
        json={"file_name": "chico.txt", "size_bytes": 10 * 1024 * 1024, "mime_type": "text/plain"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400
    assert "POST /files/upload" in resp.json()["detail"] or "upload" in resp.json()["detail"].lower()


def test_initiate_rejects_file_over_large_ceiling(client):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]

    oversized = (settings.MAX_LARGE_UPLOAD_SIZE_MB + 1) * 1024 * 1024
    resp = client.post(
        "/uploads/initiate",
        json={"file_name": "gigante.bin", "size_bytes": oversized, "mime_type": "application/octet-stream"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Flujo completo real: initiate -> subir partes REALES -> complete ->
# invisible hasta 'clean' -> se hace visible al simular el veredicto del AV.
# ---------------------------------------------------------------------------

def test_full_multipart_flow_gates_visibility_until_clean(client, db_session, presign_via_internal_minio, monkeypatch):
    import app.worker.celery_app  # noqa: F401 -- fuerza _register_all_orm_models antes de la primera query ORM

    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    # 5MB -- mínimo REAL de S3/MinIO para cualquier parte que NO sea la
    # última de un multipart (`EntityTooSmall` si se usa menos, confirmado
    # en vivo contra MinIO real armando este test con 2MB). La única parte
    # exenta de ese mínimo es la última.
    monkeypatch.setattr(settings, "LARGE_UPLOAD_PART_SIZE_BYTES", 5 * 1024 * 1024)

    creds = register_user(client)
    user = _get_orm_user(db_session, creds["email"])

    total_size = 12 * 1024 * 1024  # 12MB con partes de 5MB -> 3 partes (5, 5, 2)
    payload = UploadInitiateRequest(file_name="video_grande.mp4", size_bytes=total_size, mime_type="video/mp4")
    initiate_resp = initiate_upload(db_session, user, payload)

    assert initiate_resp.part_count == 3
    assert len(initiate_resp.part_urls) == 3
    assert initiate_resp.part_size_bytes == 5 * 1024 * 1024

    quota_mid = user_storage_quota_repo.get_by_user_id(db_session, user.id)
    assert quota_mid is not None and quota_mid.bytes_used >= total_size, "la cuota completa debe reservarse por adelantado"

    part_sizes = [5 * 1024 * 1024, 5 * 1024 * 1024, 2 * 1024 * 1024]
    completed_parts = []
    for part_url, size in zip(initiate_resp.part_urls, part_sizes):
        etag = _put_part(part_url.url, os.urandom(size))
        completed_parts.append(CompletedPartIn(part_number=part_url.part_number, etag=etag))

    file_obj = complete_upload(
        db_session, user, initiate_resp.upload_session_id, UploadCompleteRequest(parts=completed_parts)
    )

    assert file_obj.scan_status == "pending"
    assert file_obj.size_bytes == total_size

    # Invisible en TODAS las lecturas centralizadas mientras está 'pending'
    # -- ni siquiera para el propio dueño (ver docstring de CRUDFile).
    assert file_repo.get(db_session, file_obj.id) is None
    assert file_repo.get_active(db_session, file_obj.id) is None
    children = file_repo.get_children(db_session, user.id, None)
    assert file_obj.id not in {f.id for f in children}
    search_results = file_repo.search(db_session, user.id, "video_grande")
    assert file_obj.id not in {f.id for f in search_results}

    # El accessor SIN filtrar (uso exclusivo del worker de AV) sí lo ve --
    # si esto fallara, la tarea de AV del otro agente no podría ni leer el
    # archivo que tiene que escanear.
    assert file_repo.get_for_scan_worker(db_session, file_obj.id) is not None

    # Simula el veredicto del escaneo asíncrono de AV (worker del otro
    # agente, no construido en este módulo) marcando 'clean' a mano.
    scanned = file_repo.get_for_scan_worker(db_session, file_obj.id)
    scanned.scan_status = "clean"
    db_session.add(scanned)
    db_session.commit()

    assert file_repo.get(db_session, file_obj.id) is not None
    assert file_repo.get_active(db_session, file_obj.id) is not None
    children_after = file_repo.get_children(db_session, user.id, None)
    assert file_obj.id in {f.id for f in children_after}


def test_refresh_part_urls_reports_confirmed_and_missing_parts(client, db_session, presign_via_internal_minio, monkeypatch):
    import app.worker.celery_app  # noqa: F401

    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    monkeypatch.setattr(settings, "LARGE_UPLOAD_PART_SIZE_BYTES", 2 * 1024 * 1024)

    creds = register_user(client)
    user = _get_orm_user(db_session, creds["email"])

    payload = UploadInitiateRequest(file_name="reanudable.bin", size_bytes=5 * 1024 * 1024, mime_type="application/octet-stream")
    initiate_resp = initiate_upload(db_session, user, payload)
    assert initiate_resp.part_count == 3

    # Solo se sube la PRIMERA parte -- simula una conexión cortada a mitad
    # de la subida completa.
    first_part = initiate_resp.part_urls[0]
    etag_1 = _put_part(first_part.url, os.urandom(2 * 1024 * 1024))

    refreshed = refresh_part_urls(db_session, user, initiate_resp.upload_session_id)

    assert {p.part_number for p in refreshed.completed_parts} == {1}
    assert refreshed.completed_parts[0].etag == etag_1
    assert {p.part_number for p in refreshed.part_urls} == {2, 3}

    # Limpieza -- no queda una sesión in_progress colgada del resto del suite.
    abort_upload(db_session, user, initiate_resp.upload_session_id)


def test_abort_releases_reserved_quota_and_real_minio_multipart(client, db_session, presign_via_internal_minio, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)

    creds = register_user(client)
    user = _get_orm_user(db_session, creds["email"])

    quota_before = user_storage_quota_repo.get_by_user_id(db_session, user.id)
    used_before = quota_before.bytes_used if quota_before else 0

    payload = UploadInitiateRequest(file_name="cancelado.bin", size_bytes=3 * 1024 * 1024, mime_type="application/octet-stream")
    initiate_resp = initiate_upload(db_session, user, payload)

    quota_mid = user_storage_quota_repo.get_by_user_id(db_session, user.id)
    assert quota_mid.bytes_used == used_before + 3 * 1024 * 1024

    session_out = abort_upload(db_session, user, initiate_resp.upload_session_id)
    assert session_out.status == "aborted"

    quota_after = user_storage_quota_repo.get_by_user_id(db_session, user.id)
    assert quota_after.bytes_used == used_before

    # El multipart real ya no debe listarse como en curso en MinIO.
    client_minio = uploads_service.get_internal_client()
    listing = client_minio.list_multipart_uploads(Bucket=settings.MINIO_PRIVATE_BUCKET)
    open_upload_ids = {u["UploadId"] for u in listing.get("Uploads", [])}
    assert initiate_resp.upload_session_id is not None  # sanity
    from app.uploads.repository import upload_session_repo

    session_row = upload_session_repo.get(db_session, initiate_resp.upload_session_id)
    assert session_row.minio_upload_id not in open_upload_ids


def test_complete_rejects_when_actual_size_exceeds_reserved_quota(client, db_session, presign_via_internal_minio, monkeypatch):
    """El cliente declara (y reserva cuota por) 2MB pero sube 3MB reales en
    la única parte -- `complete_upload` tiene que rechazarlo de forma
    segura: NUNCA crear el `File`, liberar TODA la cuota reservada y dejar
    la sesión `'failed'` (ver `app/uploads/service.py::_fail_after_complete`,
    decisión de diseño documentada en el reporte final del agente)."""
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    monkeypatch.setattr(settings, "LARGE_UPLOAD_PART_SIZE_BYTES", 2 * 1024 * 1024)

    creds = register_user(client)
    user = _get_orm_user(db_session, creds["email"])

    quota_before = user_storage_quota_repo.get_by_user_id(db_session, user.id)
    used_before = quota_before.bytes_used if quota_before else 0

    payload = UploadInitiateRequest(file_name="mentiroso.bin", size_bytes=2 * 1024 * 1024, mime_type="application/octet-stream")
    initiate_resp = initiate_upload(db_session, user, payload)
    assert initiate_resp.part_count == 1

    # Sube 3MB reales como si fueran la única parte declarada de 2MB --
    # S3/MinIO no valida el tamaño de una parte contra nada declarado de
    # antemano, así que esto es válido a nivel de protocolo.
    etag = _put_part(initiate_resp.part_urls[0].url, os.urandom(3 * 1024 * 1024))

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        complete_upload(
            db_session, user, initiate_resp.upload_session_id,
            UploadCompleteRequest(parts=[CompletedPartIn(part_number=1, etag=etag)]),
        )
    assert exc_info.value.status_code == 413

    quota_after = user_storage_quota_repo.get_by_user_id(db_session, user.id)
    assert quota_after.bytes_used == used_before, "la cuota reservada debe liberarse COMPLETA ante el rechazo"

    from app.uploads.repository import upload_session_repo

    session_row = upload_session_repo.get(db_session, initiate_resp.upload_session_id)
    assert session_row.status == "failed"
    assert session_row.file_id is None


# ---------------------------------------------------------------------------
# Ownership -- vía HTTP real, dos usuarios distintos.
# ---------------------------------------------------------------------------

def test_ownership_isolation_via_http(client):
    creds_a = register_user(client)
    token_a = login_user(client, creds_a["email"], creds_a["password"]).json()["data"]["access_token"]

    creds_b = register_user(client)
    token_b = login_user(client, creds_b["email"], creds_b["password"]).json()["data"]["access_token"]

    init_resp = client.post(
        "/uploads/initiate",
        json={"file_name": "de_a.bin", "size_bytes": 200 * 1024 * 1024, "mime_type": "application/octet-stream"},
        headers=auth_headers(token_a),
    )
    assert init_resp.status_code == 201
    session_id = init_resp.json()["upload_session_id"]

    # B intenta tocar la sesión de A -- 404 en los tres endpoints (nunca
    # 403: no hay que confirmarle a B que el id existe, mismo criterio
    # anti-IDOR que `_get_owned_file`).
    for path, body in [
        (f"/uploads/{session_id}/refresh-part-urls", None),
        (f"/uploads/{session_id}/complete", {"parts": [{"part_number": 1, "etag": "\"x\""}]}),
        (f"/uploads/{session_id}/abort", None),
    ]:
        resp = client.post(path, json=body, headers=auth_headers(token_b))
        assert resp.status_code == 404, f"{path} debería devolver 404 para un usuario ajeno, dio {resp.status_code}"

    # A sí puede abortar la suya.
    resp = client.post(f"/uploads/{session_id}/abort", headers=auth_headers(token_a))
    assert resp.status_code == 200
    assert resp.json()["status"] == "aborted"


# ---------------------------------------------------------------------------
# Tarea periódica de limpieza de sesiones abandonadas.
# ---------------------------------------------------------------------------

def test_cleanup_task_aborts_expired_sessions_and_releases_quota(client, db_session, presign_via_internal_minio, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.uploads.repository import upload_session_repo
    from app.worker.tasks.uploads import cleanup_abandoned_upload_sessions

    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)

    creds = register_user(client)
    user = _get_orm_user(db_session, creds["email"])

    quota_before = user_storage_quota_repo.get_by_user_id(db_session, user.id)
    used_before = quota_before.bytes_used if quota_before else 0

    payload = UploadInitiateRequest(file_name="abandonado.bin", size_bytes=2 * 1024 * 1024, mime_type="application/octet-stream")
    initiate_resp = initiate_upload(db_session, user, payload)

    # Fuerza el vencimiento -- sin esperar las 48hs reales configuradas
    # (settings.UPLOAD_SESSION_EXPIRY_HOURS).
    session_row = upload_session_repo.get(db_session, initiate_resp.upload_session_id)
    session_row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.add(session_row)
    db_session.commit()

    cleanup_abandoned_upload_sessions()

    db_session.refresh(session_row)
    assert session_row.status == "aborted"

    quota_after = user_storage_quota_repo.get_by_user_id(db_session, user.id)
    assert quota_after.bytes_used == used_before

    client_minio = uploads_service.get_internal_client()
    listing = client_minio.list_multipart_uploads(Bucket=settings.MINIO_PRIVATE_BUCKET)
    open_upload_ids = {u["UploadId"] for u in listing.get("Uploads", [])}
    assert session_row.minio_upload_id not in open_upload_ids


# ---------------------------------------------------------------------------
# Regresión de la revisión adversarial de seguridad (hallazgo ALTO): un solo
# usuario podía acaparar TODO el cupo global de admisión abriendo sesiones
# sin completar/abortar, y el TTL del cupo estaba atado a las 48hs de
# `expires_at` en vez de un lease corto -- bloqueaba la feature para todos
# los demás usuarios hasta 48-54hs. Estos tres tests reproducen el mismo
# escenario que usó el revisor, contra Redis real (nunca mockeado).
# ---------------------------------------------------------------------------

def _initiate_direct(db_session, user, *, name_suffix: str, size_mb: int = 200):
    payload = UploadInitiateRequest(
        file_name=f"acaparado_{name_suffix}.bin", size_bytes=size_mb * 1024 * 1024, mime_type="application/octet-stream"
    )
    return initiate_upload(db_session, user, payload)


def test_per_user_admission_cap_isolated_from_other_users(client, db_session, monkeypatch):
    """Reproduce el repro EXACTO del revisor: un usuario abre sesiones sin
    completar/abortar hasta llenar SU cupo -- el próximo `/initiate` de ESE
    mismo usuario tiene que dar 503, pero un usuario DISTINTO tiene que
    poder iniciar la suya sin problema (antes del fix, el cupo era 100%
    global: el primer usuario podía agotar TODO, bloqueando también al
    segundo)."""
    import app.worker.celery_app  # noqa: F401 -- fuerza _register_all_orm_models antes de la primera query ORM

    monkeypatch.setattr(settings, "MAX_CONCURRENT_LARGE_UPLOADS_PER_USER", 2)
    monkeypatch.setattr(settings, "MAX_CONCURRENT_LARGE_UPLOADS", 50)  # el global no debe ser el factor limitante acá

    creds_a = register_user(client)
    user_a = _get_orm_user(db_session, creds_a["email"])
    creds_b = register_user(client)
    user_b = _get_orm_user(db_session, creds_b["email"])

    opened = []
    try:
        # Usuario A llena SU propio cupo (2) sin completar ni abortar nada.
        for i in range(2):
            resp = _initiate_direct(db_session, user_a, name_suffix=f"a{i}")
            opened.append((user_a, resp.upload_session_id))

        # Una tercera sesión del MISMO usuario A -- 503, cupo por-usuario lleno.
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _initiate_direct(db_session, user_a, name_suffix="a-blocked")
        assert exc_info.value.status_code == 503

        # Usuario B, sin relación con A, tiene que poder iniciar la SUYA sin
        # problema -- esto es lo que el bug rompía (cupo 100% global).
        resp_b = _initiate_direct(db_session, user_b, name_suffix="b0")
        opened.append((user_b, resp_b.upload_session_id))
    finally:
        for user, session_id in opened:
            try:
                abort_upload(db_session, user, session_id)
            except Exception:
                pass


def test_admission_slot_self_heals_via_short_lease_before_periodic_cleanup(client, db_session, monkeypatch):
    """El cupo de concurrencia (no la fila en DB, esa la limpia la tarea
    periódica cada 6hs) tiene que autorecuperarse mucho antes de esas 6hs
    cuando una sesión queda abandonada -- gracias a un lease CORTO
    (`LARGE_UPLOAD_ADMISSION_LEASE_HOURS`) desacoplado de las 48hs de
    `expires_at`. Acá se fuerza un lease de ~1 segundo (monkeypatch directo
    sobre el objeto `settings`, sin pasar por la validación de Pydantic --
    el código solo hace `* 3600` sobre el valor, funciona igual con un
    float) para no tener que esperar horas reales en el test."""
    import app.worker.celery_app  # noqa: F401

    monkeypatch.setattr(settings, "MAX_CONCURRENT_LARGE_UPLOADS_PER_USER", 1)
    monkeypatch.setattr(settings, "MAX_CONCURRENT_LARGE_UPLOADS", 50)
    monkeypatch.setattr(settings, "LARGE_UPLOAD_ADMISSION_LEASE_HOURS", 1 / 3600)  # ~1 segundo

    creds = register_user(client)
    user = _get_orm_user(db_session, creds["email"])

    resp_1 = _initiate_direct(db_session, user, name_suffix="lease1")

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        _initiate_direct(db_session, user, name_suffix="lease-blocked")
    assert exc_info.value.status_code == 503

    import time as time_module

    time_module.sleep(1.5)  # deja vencer el lease corto (~1s)

    # Sin esperar las 6hs de la tarea periódica ni llamar a
    # cleanup_abandoned_upload_sessions -- el PROPIO chequeo de admisión de
    # /initiate poda (ZREMRANGEBYSCORE) los miembros vencidos antes de
    # contar. Si esto todavía diera 503, el cupo NO se estaría autorecuperando.
    resp_2 = _initiate_direct(db_session, user, name_suffix="lease2")

    abort_upload(db_session, user, resp_1.upload_session_id)
    abort_upload(db_session, user, resp_2.upload_session_id)


def test_refresh_part_urls_renews_admission_lease(client, db_session, presign_via_internal_minio, monkeypatch):
    """`refresh-part-urls` tiene que EXTENDER el lease corto de admisión
    (no el `expires_at` de 48hs de la sesión) -- confirma leyendo el score
    real del ZSET de Redis antes y después."""
    import app.worker.celery_app  # noqa: F401

    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)

    redis_client = uploads_service.cache.client
    assert redis_client is not None, "Este test necesita Redis real disponible"

    creds = register_user(client)
    user = _get_orm_user(db_session, creds["email"])

    resp = _initiate_direct(db_session, user, name_suffix="renew", size_mb=200)
    session_id = resp.upload_session_id

    score_before = redis_client.zscore(uploads_service._ADMISSION_KEY, str(session_id))
    user_score_before = redis_client.zscore(uploads_service._user_admission_key(user.id), str(session_id))
    assert score_before is not None, "la sesión recién creada debería tener su lugar reservado en el ZSET global"
    assert user_score_before is not None, "y también en el ZSET por-usuario"

    import time as time_module

    time_module.sleep(1.1)  # margen real para que el score nuevo sea estrictamente mayor
    refresh_part_urls(db_session, user, session_id)

    score_after = redis_client.zscore(uploads_service._ADMISSION_KEY, str(session_id))
    user_score_after = redis_client.zscore(uploads_service._user_admission_key(user.id), str(session_id))
    assert score_after is not None and score_after > score_before
    assert user_score_after is not None and user_score_after > user_score_before

    abort_upload(db_session, user, session_id)
