"""`scan_uploaded_file(file_id, tenant_schema=None)`: propagación del schema
del tenant (modo cloud). NO hay entorno cloud real -- estos tests son
unitarios (monkeypatch), no verificados en vivo contra multi-tenant."""
import contextlib
import uuid



def _patch_worker_db(monkeypatch):
    """Reemplaza `get_worker_db` por un fake que registra el schema y cede un
    objeto opaco; `get_for_scan_worker` devuelve None ("archivo inexistente"),
    así la tarea termina por su camino REAL de retorno temprano, sin excepción
    ni try/except en el test. Cubre: el schema llega a get_worker_db. No
    cubre el escaneo/cuarentena (eso lo hace test_av_scan_async.py)."""
    from app.files.repository import file_repo
    from app.worker.tasks import av_scan

    seen = []

    @contextlib.contextmanager
    def _fake_worker_db(schema_name=None):
        seen.append(schema_name)
        yield object()

    monkeypatch.setattr(av_scan, "get_worker_db", _fake_worker_db)
    monkeypatch.setattr(av_scan, "_try_acquire_scan_slot", lambda: True)
    monkeypatch.setattr(av_scan, "_release_scan_slot", lambda: None)
    monkeypatch.setattr(file_repo, "get_for_scan_worker", lambda db, fid: None)
    return seen


def test_task_passes_tenant_schema_to_get_worker_db(monkeypatch):
    from app.worker.tasks import av_scan

    seen = _patch_worker_db(monkeypatch)
    av_scan.scan_uploaded_file(str(uuid.uuid4()), "tenant_x")
    assert seen == ["tenant_x"]


def test_task_accepts_single_argument_for_already_queued_messages(monkeypatch):
    from app.worker.tasks import av_scan

    seen = _patch_worker_db(monkeypatch)
    av_scan.scan_uploaded_file(str(uuid.uuid4()))
    assert seen == [None]


def test_requeue_for_concurrency_propagates_tenant_schema(monkeypatch):
    from app.worker.tasks import av_scan

    calls = []
    monkeypatch.setattr(av_scan, "_try_acquire_scan_slot", lambda: False)
    monkeypatch.setattr(
        av_scan.scan_uploaded_file, "apply_async", lambda args, countdown: calls.append((args, countdown))
    )
    fid = str(uuid.uuid4())
    av_scan.scan_uploaded_file(fid, "tenant_x")
    assert calls == [([fid, "tenant_x"], av_scan.AV_SCAN_REQUEUE_COUNTDOWN_SECONDS)]


def test_enqueue_av_scan_from_uploads_uses_tenant_schema_ctx(monkeypatch):
    from app.core.database import tenant_schema_ctx
    from app.uploads.service import _enqueue_av_scan
    from app.worker.tasks import av_scan

    calls = []
    monkeypatch.setattr(av_scan.scan_uploaded_file, "delay", lambda *a, **k: calls.append((a, k)))
    fid = uuid.uuid4()
    token = tenant_schema_ctx.set("tenant_x")
    try:
        _enqueue_av_scan(fid)
    finally:
        tenant_schema_ctx.reset(token)
    _enqueue_av_scan(fid)  # sin schema (modo local)
    assert calls[0] == ((str(fid), "tenant_x"), {})
    assert calls[1] == ((str(fid), None), {})
