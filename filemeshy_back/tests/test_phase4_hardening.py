"""Hallazgos de la revisión adversarial (Fase 4): ventana fija del
RateLimiter, SoftTimeLimit dentro de los bucles de extracción, barrido de
filas 'pending' huérfanas, register_attempt atómico."""
import io
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import text

from conftest import auth_headers, login_user, register_user


# ---------------------------------------------------------- ventana fija

@pytest.fixture(params=["redis", "memory"])
def limiter(request, monkeypatch):
    from app.auth.service import RateLimiter

    if request.param == "memory":
        monkeypatch.setattr(RateLimiter, "_get_redis", staticmethod(lambda: None))
    elif RateLimiter._get_redis() is None:
        pytest.skip("Redis no disponible")
    return RateLimiter


def test_fixed_window_blocks_then_resets_when_window_expires(limiter):
    key = f"pytest_fw:{uuid.uuid4().hex}"
    assert [limiter.check_fixed_window(key, 3, 2)[0] for _ in range(3)] == [True] * 3
    assert limiter.check_fixed_window(key, 3, 2)[0] is False
    time.sleep(2.3)
    assert limiter.check_fixed_window(key, 3, 2)[0] is True  # ventana nueva


def test_fixed_window_is_not_renewed_by_spaced_requests(limiter):
    """Con TTL renovado en cada request (bug anterior), requests espaciadas
    menos que la ventana bloqueaban para siempre. Con ventana fija, la
    ventana vence 2s después de la PRIMERA request."""
    key = f"pytest_fw:{uuid.uuid4().hex}"
    assert limiter.check_fixed_window(key, 3, 2)[0] is True   # t=0, count 1
    time.sleep(1.2)
    assert limiter.check_fixed_window(key, 3, 2)[0] is True   # t=1.2, count 2
    time.sleep(1.1)                                            # t=2.3 > ventana
    results = [limiter.check_fixed_window(key, 3, 2)[0] for _ in range(4)]
    assert results == [True, True, True, False]


# ---------------------------------------------------------- helpers indexación

def _upload_txt(client, db_session):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": ("pytest_p4.txt", io.BytesIO(b"contenido"), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    file_id = resp.json()["id"]
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        row = _row(db_session, file_id)
        if row is not None and row[0] != "pending":
            break
        time.sleep(0.3)
    time.sleep(0.5)  # el worker real ya terminó
    return file_id


def _row(db_session, file_id):
    db_session.rollback()
    return db_session.execute(
        text("SELECT extraction_status, attempts, error_message FROM file_content_index WHERE file_id = :f"),
        {"f": file_id},
    ).first()


def _run(file_id):
    from app.worker.tasks.indexing import index_file_content

    index_file_content(None, file_id)


def _make_pdf(db_session, file_id):
    db_session.execute(
        text("UPDATE files SET mime_type = 'application/pdf' WHERE id = :f"), {"f": file_id}
    )
    db_session.commit()


class _Page:
    def __init__(self, fn):
        self._fn = fn

    def extract_text(self):
        return self._fn()


def _reader_with(pages):
    class _Reader:
        def __init__(self, *_a, **_k):
            self.pages = pages

    return _Reader


# ---------------------------------------------------------- tarea 1

def test_soft_time_limit_inside_pdf_text_loop_is_not_swallowed(client, db_session, monkeypatch):
    import pypdf
    from app.worker.tasks import indexing

    file_id = _upload_txt(client, db_session)
    _make_pdf(db_session, file_id)

    def _slow():
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(pypdf, "PdfReader", _reader_with([_Page(_slow)]))
    monkeypatch.setattr(indexing, "_read_private_object", lambda key: b"%PDF")
    _run(file_id)
    status, _, msg = _row(db_session, file_id)
    assert status == "failed"
    assert "tiempo" in msg


def test_soft_time_limit_inside_ocr_loop_is_not_swallowed(client, db_session, monkeypatch):
    import pdf2image
    import pypdf
    import pytesseract
    from app.worker.tasks import indexing

    file_id = _upload_txt(client, db_session)
    _make_pdf(db_session, file_id)

    # Sin texto embebido -> cae al OCR; la imagen "renderizada" es opaca.
    monkeypatch.setattr(pypdf, "PdfReader", _reader_with([_Page(lambda: "")]))
    monkeypatch.setattr(pdf2image, "convert_from_bytes", lambda *a, **k: [object()])

    def _ocr(*_a, **_k):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(pytesseract, "image_to_string", _ocr)
    monkeypatch.setattr(indexing, "_read_private_object", lambda key: b"%PDF")
    _run(file_id)
    status, _, msg = _row(db_session, file_id)
    assert status == "failed"
    assert "tiempo" in msg


# ---------------------------------------------------------- tarea 2

def _set_state(db_session, file_id, status, minutes_ago):
    db_session.execute(
        text(
            "UPDATE file_content_index SET extraction_status = :s, "
            "attempted_at = :t WHERE file_id = :f"
        ),
        {"s": status, "t": datetime.now(timezone.utc) - timedelta(minutes=minutes_ago), "f": file_id},
    )
    db_session.commit()


def test_sweep_marks_only_stale_pending_rows_failed(client, db_session):
    from app.worker.tasks.maintenance import sweep_stale_pending_content_index

    stale = _upload_txt(client, db_session)
    recent = _upload_txt(client, db_session)
    done = _upload_txt(client, db_session)
    _set_state(db_session, stale, "pending", 60)
    _set_state(db_session, recent, "pending", 1)
    _set_state(db_session, done, "done", 600)

    sweep_stale_pending_content_index()

    assert _row(db_session, stale)[0] == "failed"
    assert "minutos" in _row(db_session, stale)[2]
    assert _row(db_session, recent)[0] == "pending"
    assert _row(db_session, done)[0] == "done"


def test_sweep_is_scheduled_and_routed():
    from app.worker.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["sweep-stale-pending-content-index"]
    assert entry["task"] == "app.worker.tasks.maintenance.sweep_stale_pending_content_index"
    assert entry["options"]["queue"] == "maintenance"
    from app.worker.tasks.maintenance import INDEX_PENDING_STALE_MINUTES

    assert INDEX_PENDING_STALE_MINUTES * 60 > 180 * 2  # holgura sobre el hard limit


# ---------------------------------------------------------- tarea 7

def test_register_attempt_is_atomic_upsert_returning_previous_value(client, db_session):
    from app.files.repository import file_content_index_repo

    file_id = _upload_txt(client, db_session)
    db_session.execute(text("DELETE FROM file_content_index WHERE file_id = :f"), {"f": file_id})
    db_session.commit()

    fid = uuid.UUID(file_id)
    # Fila inexistente: la crea, sin IntegrityError, devuelve 0.
    assert file_content_index_repo.register_attempt(db_session, fid) == 0
    assert _row(db_session, file_id)[:2] == ("pending", 1)
    assert file_content_index_repo.register_attempt(db_session, fid) == 1
    assert file_content_index_repo.register_attempt(db_session, fid) == 2
    assert _row(db_session, file_id)[1] == 3


# ---------------------------------------------------------- purga memoria

def test_memory_fixed_windows_are_purged_and_hard_capped(monkeypatch):
    from app.auth import service
    from app.auth.service import RateLimiter

    monkeypatch.setattr(RateLimiter, "_get_redis", staticmethod(lambda: None))
    monkeypatch.setattr(service, "MEMORY_FIXED_WINDOWS_MAX_ENTRIES", 50)
    monkeypatch.setattr(service, "_memory_fixed_windows", {})
    store = service._memory_fixed_windows

    # Atacante activo: ventana larga, ya bloqueado (limite 2).
    for _ in range(3):
        RateLimiter.check_fixed_window("pytest_attacker", 2, 3600)
    assert RateLimiter.check_fixed_window("pytest_attacker", 2, 3600)[0] is False

    # 80 claves con ventana corta; se dejan vencer.
    for i in range(80):
        RateLimiter.check_fixed_window(f"pytest_short:{i}", 5, 1)
    time.sleep(1.2)
    RateLimiter.check_fixed_window("pytest_trigger", 5, 1)  # dispara la purga
    assert len(store) < 50
    # El atacante vigente conserva su contador: sigue bloqueado.
    assert RateLimiter.check_fixed_window("pytest_attacker", 2, 3600)[0] is False

    # Cota dura: muchas claves vigentes -> descarta las MÁS VIEJAS, no la reciente.
    for i in range(120):
        RateLimiter.check_fixed_window(f"pytest_live:{i}", 5, 3600)
    RateLimiter.check_fixed_window("pytest_trigger2", 5, 3600)
    assert len(store) <= 51
    assert "pytest_live:119" in store
    assert "pytest_live:0" not in store
