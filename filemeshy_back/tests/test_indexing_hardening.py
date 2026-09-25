"""Endurecimiento de `index_file_content` / `_extract_pdf_text`:
tope de páginas de texto PDF, tope de intentos contra redelivery indefinida
(`attempts`), SoftTimeLimitExceeded propio, tope de tamaño.

La tarea se invoca directo (síncrona, sin broker). Antes de manipular
`attempts` se espera a que el worker real termine la indexación que encola
la propia subida (para que no pise el estado que fija el test)."""
import io
import time

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import text

from conftest import auth_headers, login_user, register_user


def _upload_txt(client, db_session):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": ("pytest_hardening.txt", io.BytesIO(b"contenido indexable"), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    file_id = resp.json()["id"]
    # Esperar al worker real (estado terminal) para no competir con él.
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        row = _index_row(db_session, file_id)
        if row is not None and row[0] != "pending":
            break
        time.sleep(0.3)
    time.sleep(0.5)
    return file_id


def _index_row(db_session, file_id):
    db_session.rollback()
    return db_session.execute(
        text("SELECT extraction_status, attempts, error_message FROM file_content_index WHERE file_id = :f"),
        {"f": file_id},
    ).first()


def _set_attempts(db_session, file_id, value):
    db_session.execute(
        text("UPDATE file_content_index SET attempts = :a, extraction_status = 'pending' WHERE file_id = :f"),
        {"a": value, "f": file_id},
    )
    db_session.commit()


def _run(file_id):
    from app.worker.tasks.indexing import index_file_content

    index_file_content(None, file_id)


# ---------------------------------------------------------------- tarea 3

class _FakePage:
    def __init__(self, text_value, counter):
        self._t, self._c = text_value, counter

    def extract_text(self):
        self._c.append(1)
        return self._t


def _fake_reader(pages_text, counter):
    class _Reader:
        def __init__(self, *_a, **_k):
            self.pages = [_FakePage(t, counter) for t in pages_text]

    return _Reader


def test_pdf_text_extraction_stops_at_page_cap(monkeypatch):
    import pypdf
    from app.worker.tasks import indexing

    calls = []
    monkeypatch.setattr(pypdf, "PdfReader", _fake_reader(["a", "b", "c"], calls))
    monkeypatch.setattr(indexing, "MAX_PDF_TEXT_PAGES", 2)
    assert indexing._extract_pdf_text(b"%PDF") == "a\nb"
    assert len(calls) == 2


def test_pdf_text_extraction_stops_at_char_cap(monkeypatch):
    import pypdf
    from app.worker.tasks import indexing

    calls = []
    monkeypatch.setattr(pypdf, "PdfReader", _fake_reader(["x" * 50, "y" * 50, "z" * 50], calls))
    monkeypatch.setattr(indexing, "MAX_CONTENT_CHARS", 60)
    indexing._extract_pdf_text(b"%PDF")
    assert len(calls) == 2  # tras la 2a página ya hay >= 60 chars


# ---------------------------------------------------------------- tarea 4

def test_task_config_reject_on_worker_lost_false_only_for_indexing():
    from app.worker.celery_app import celery_app
    from app.worker.tasks.indexing import index_file_content

    assert index_file_content.reject_on_worker_lost is False
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert index_file_content.soft_time_limit == 120
    assert index_file_content.time_limit == 180


def test_max_attempts_marks_failed_without_processing(client, db_session, monkeypatch):
    from app.worker.tasks import indexing

    file_id = _upload_txt(client, db_session)
    _set_attempts(db_session, file_id, indexing.MAX_INDEX_ATTEMPTS)

    def _boom(*_a, **_k):
        raise AssertionError("no debe procesar con attempts >= MAX")

    monkeypatch.setattr(indexing, "_extract_text_for_mime", _boom)
    monkeypatch.setattr(indexing, "_read_private_object", _boom)
    _run(file_id)

    status, attempts, msg = _index_row(db_session, file_id)
    assert status == "failed"
    assert "intentos" in msg
    assert attempts >= indexing.MAX_INDEX_ATTEMPTS


def test_success_resets_attempts(client, db_session):
    file_id = _upload_txt(client, db_session)
    _set_attempts(db_session, file_id, 2)
    _run(file_id)
    status, attempts, _ = _index_row(db_session, file_id)
    assert status == "done"
    assert attempts == 0


def test_attempt_counter_is_committed_before_processing(client, db_session, monkeypatch):
    """Si el proceso muere durante la extracción, el intento ya quedó contado."""
    from app.worker.tasks import indexing

    file_id = _upload_txt(client, db_session)
    _set_attempts(db_session, file_id, 0)

    def _crash(*_a, **_k):
        raise KeyboardInterrupt  # simula caída dura (no es Exception)

    monkeypatch.setattr(indexing, "_extract_text_for_mime", _crash)
    with pytest.raises(KeyboardInterrupt):
        _run(file_id)
    assert _index_row(db_session, file_id)[1] == 1


def test_soft_time_limit_persists_failed_with_message(client, db_session, monkeypatch):
    from app.worker.tasks import indexing

    file_id = _upload_txt(client, db_session)

    def _slow(*_a, **_k):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(indexing, "_extract_text_for_mime", _slow)
    _run(file_id)
    status, _, msg = _index_row(db_session, file_id)
    assert status == "failed"
    assert "tiempo" in msg and "120" in msg


def test_oversized_file_is_not_read(client, db_session, monkeypatch):
    from app.worker.tasks import indexing

    file_id = _upload_txt(client, db_session)

    def _boom(*_a, **_k):
        raise AssertionError("no debe leer el objeto si excede el tope")

    monkeypatch.setattr(indexing, "INDEXING_MAX_SIZE_BYTES", 1)
    monkeypatch.setattr(indexing, "_read_private_object", _boom)
    _run(file_id)
    status, _, msg = _index_row(db_session, file_id)
    assert status == "unsupported"
    assert "grande" in msg


def test_enqueue_resets_attempts(client, db_session, monkeypatch):
    from uuid import UUID
    from app.files.router import _enqueue_content_indexing
    from app.worker.tasks import indexing

    file_id = _upload_txt(client, db_session)
    _set_attempts(db_session, file_id, 2)
    monkeypatch.setattr(indexing.index_file_content, "delay", lambda *a, **k: None)
    _enqueue_content_indexing(UUID(file_id))
    assert _index_row(db_session, file_id)[1] == 0
