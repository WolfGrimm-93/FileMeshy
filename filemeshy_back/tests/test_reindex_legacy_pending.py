"""Ronda 12 (B3) -- scripts/reindex_legacy_pending.py.

Filas legadas 'pending' con `attempted_at IS NULL` (nadie las barre). El
script las re-encola (archivo vivo) o las marca failed (archivo borrado).
Cada test acota el script a SUS file_ids (`only_file_ids`) para no tocar filas
reales de otros datos del stack."""
import io

import pytest
import time
from uuid import UUID

from sqlalchemy import text

from conftest import auth_headers, login_user, register_user

from scripts.reindex_legacy_pending import MSG_FILE_MISSING, reindex_legacy_pending


_CREATED_FILE_IDS: list[str] = []


@pytest.fixture(autouse=True)
def _cleanup_legacy_rows(db_session):
    """Estos tests FUERZAN filas 'pending' con attempted_at NULL (estado legado).
    Sin limpieza quedaban en la BD del stack y el script real las volvía a ver
    (origen de las filas "nuevas" reportadas en la auditoría): al terminar, se
    marcan failed con attempted_at para que ninguna corrida deje filas legadas."""
    yield
    ids = list(_CREATED_FILE_IDS)
    _CREATED_FILE_IDS.clear()
    if not ids:
        return
    db_session.rollback()
    db_session.execute(
        text("UPDATE file_content_index SET extraction_status='failed', attempted_at=now(), "
             "error_message='pytest cleanup' WHERE CAST(file_id AS text) = ANY(:ids) "
             "AND extraction_status='pending' AND attempted_at IS NULL"),
        {"ids": ids},
    )
    db_session.commit()


def _upload(client, token, name):
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": (name, io.BytesIO(b"contenido legado " + name.encode()), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    _CREATED_FILE_IDS.append(resp.json()["id"])
    return resp.json()["id"]


def _wait_indexed(db_session, file_id, timeout=45.0):
    """Espera a que el worker real termine la indexacion normal del upload,
    para poder forzar DESPUES el estado legado sin carreras."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        db_session.expire_all()
        row = db_session.execute(
            text("SELECT extraction_status FROM file_content_index WHERE file_id = :f"), {"f": file_id}
        ).first()
        if row and row[0] != "pending":
            time.sleep(0.5)  # margen: que el worker termine de commitear antes de forzar el estado legado
            return
        time.sleep(0.3)
    raise AssertionError("el worker no indexo a tiempo")


def _force_legacy(db_session, file_id):
    db_session.execute(
        text(
            "UPDATE file_content_index SET extraction_status='pending', attempted_at=NULL, "
            "attempts=2, error_message=NULL WHERE file_id = :f"
        ),
        {"f": file_id},
    )
    db_session.commit()


def _row(db_session, file_id):
    db_session.expire_all()
    return db_session.execute(
        text("SELECT extraction_status, attempted_at, attempts, error_message FROM file_content_index WHERE file_id = :f"),
        {"f": file_id},
    ).first()


def _setup(client, db_session):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    alive = _upload(client, token, "pytest_legacy_vivo.txt")
    dead = _upload(client, token, "pytest_legacy_borrado.txt")
    for f in (alive, dead):
        _wait_indexed(db_session, f)
    db_session.execute(text("UPDATE files SET deleted_at = now() WHERE id = :f"), {"f": dead})
    db_session.commit()
    for f in (alive, dead):
        _force_legacy(db_session, f)
    return alive, dead


def test_dry_run_changes_nothing_and_enqueues_nothing(client, db_session):
    alive, dead = _setup(client, db_session)
    calls = []
    res = reindex_legacy_pending(
        dry_run=True, enqueue=lambda s, f: calls.append(f), only_file_ids=[UUID(alive), UUID(dead)]
    )
    assert res["found"] == 2 and res["requeued"] == 1 and res["failed"] == 1
    assert calls == []
    for f in (alive, dead):
        status, attempted_at, attempts, _ = _row(db_session, f)
        assert status == "pending" and attempted_at is None and attempts == 2


def test_real_run_requeues_live_file_and_fails_deleted_one(client, db_session):
    alive, dead = _setup(client, db_session)
    calls = []
    res = reindex_legacy_pending(
        dry_run=False, enqueue=lambda s, f: calls.append(f), only_file_ids=[UUID(alive), UUID(dead)]
    )
    assert res == {"found": 2, "requeued": 1, "failed": 1, "enqueue_errors": 0}
    assert calls == [alive]

    status, attempted_at, attempts, _ = _row(db_session, alive)
    assert status == "pending" and attempts == 0  # reseteado; lo procesa el worker

    status, attempted_at, _, message = _row(db_session, dead)
    assert status == "failed" and attempted_at is not None and message == MSG_FILE_MISSING

    # Idempotente: el borrado ya no aparece; el vivo (sin worker en este
    # test) se re-encolaria otra vez sin dano.
    again = reindex_legacy_pending(
        dry_run=False, enqueue=lambda s, f: None, only_file_ids=[UUID(alive), UUID(dead)]
    )
    assert again["failed"] == 0 and again["found"] == 1


def test_real_run_with_real_worker_ends_with_attempted_at(client, db_session):
    """Camino completo: el script encola de verdad (Celery) y el worker
    procesa -> la fila queda 'done' con attempted_at seteado."""
    alive, _ = _setup(client, db_session)
    reindex_legacy_pending(dry_run=False, only_file_ids=[UUID(alive)])
    deadline = time.time() + 30
    while time.time() < deadline:
        status, attempted_at, *_ = _row(db_session, alive)
        if status != "pending":
            break
        time.sleep(0.5)
    assert status == "done" and attempted_at is not None


# ---- Fase 4: --all-schemas y guard del UPDATE de filas vivas ----------------

def test_all_schemas_aggregates_per_schema(monkeypatch):
    """`reindex_all_schemas` recorre los schemas y suma los totales; el
    dry-run no escribe nada (reindex_legacy_pending se sustituye por un
    registro de llamadas)."""
    import scripts.reindex_legacy_pending as mod

    calls = []

    def fake(*, dry_run, schema=None, enqueue=None, only_file_ids=None):
        calls.append((schema, dry_run))
        return {"found": 2, "requeued": 1, "failed": 1, "enqueue_errors": 0}

    monkeypatch.setattr(mod, "reindex_legacy_pending", fake)
    total = mod.reindex_all_schemas(dry_run=True, schemas=["tenant_a", "tenant_b"])
    assert calls == [("tenant_a", True), ("tenant_b", True)]
    assert total["found"] == 4 and total["requeued"] == 2 and total["failed"] == 2
    assert set(total["per_schema"]) == {"tenant_a", "tenant_b"}


def test_all_schemas_local_mode_runs_default_schema_once(monkeypatch, client, db_session):
    """En modo local `iter_tenant_schemas()` da un único None (schema por
    defecto): --all-schemas equivale a la corrida normal."""
    import scripts.reindex_legacy_pending as mod
    from app.core.config import settings

    if settings.DEPLOYMENT_MODE == "cloud":
        pytest.skip("solo aplica en modo local")
    alive, dead = _setup(client, db_session)
    total = mod.reindex_all_schemas(dry_run=True)
    assert set(total["per_schema"]) == {"public"}
    assert total["found"] >= 2
    for f in (alive, dead):  # dry-run: nada cambia
        assert _row(db_session, f)[0] == "pending" and _row(db_session, f)[1] is None


def test_live_update_does_not_reset_attempts_of_row_taken_by_worker(client, db_session, monkeypatch):
    """Carrera: el worker toma la fila (attempted_at seteado, attempts>0) ENTRE
    el SELECT y el UPDATE. Sin el guard, el UPDATE le reseteaba attempts=0."""
    alive, _ = _setup(client, db_session)
    import scripts.reindex_legacy_pending as mod

    real_worker_db = mod.get_worker_db
    state = {"done": False}

    class _Wrap:
        """Envuelve la sesión: tras el SELECT inicial simula al worker."""
        def __init__(self, db):
            self._db = db

        def execute(self, stmt, params=None):
            res = self._db.execute(stmt, params) if params is not None else self._db.execute(stmt)
            if not state["done"] and "SELECT i.file_id" in str(stmt):
                state["done"] = True
                rows = res.all()
                other = db_session  # sesión independiente (otra conexión)
                other.execute(
                    text("UPDATE file_content_index SET attempted_at = now(), attempts = 2 WHERE file_id = :f"),
                    {"f": alive},
                )
                other.commit()

                class _Rows:
                    def all(self_inner):
                        return rows
                return _Rows()
            return res

        def commit(self):
            self._db.commit()

    from contextlib import contextmanager

    @contextmanager
    def wrapped(schema_name=None):
        with real_worker_db(schema_name=schema_name) as db:
            yield _Wrap(db)

    monkeypatch.setattr(mod, "get_worker_db", wrapped)
    mod.reindex_legacy_pending(dry_run=False, enqueue=lambda s, f: None, only_file_ids=[UUID(alive)])
    _, attempted_at, attempts, _msg = _row(db_session, alive)
    assert attempts == 2 and attempted_at is not None
