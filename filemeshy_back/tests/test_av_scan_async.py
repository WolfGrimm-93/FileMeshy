"""Ronda 9 -- escaneo antivirus ASÍNCRONO de archivos grandes
(`app.worker.tasks.av_scan.scan_uploaded_file`).

Este archivo NO ejercita el flujo HTTP completo de subida multipart
(`app/uploads/`, de otro agente/módulo) -- eso lo cubre la suite de ese
módulo. Acá se prueba la tarea de escaneo en sí, de forma aislada: se
sube contenido DIRECTO a MinIO (bucket privado, mismo mecanismo que usa la
app real, `upload_private_file`) y se crea la fila `File` a mano con
`scan_status='pending'` (el estado en el que la deja `app/uploads/service.py`
al completar una subida grande) -- exactamente el punto de partida real que
ve `scan_uploaded_file` en producción.

La tarea se invoca DIRECTO como objeto Celery (no `.delay()`, sin broker
real) -- mismo patrón que `tests/test_content_indexing.py`/
`tests/test_purge_file_versions_quota.py` para tareas sin endpoint HTTP
dedicado. Al ser `bind=True`, llamar `scan_uploaded_file(file_id)` (sin
pasar `self`) hace que Celery inyecte automáticamente una instancia real de
`self` -- confirmado en vivo, mismo mecanismo que ya usan esos otros tests
para `index_file_content`/`purge_deleted_files_and_folders`.

Contra `clamd` REAL (sin mocks, mismo criterio que `test_antivirus_scan.py`)
para los casos de contenido limpio/EICAR. El caso de `clamd` caído usa un
doble liviano de la tarea Celery (no el broker real) para poder controlar
`self.request.retries` de forma determinística sin depender de reintentos
reales con backoff de minutos -- ver `_FakeTask`."""
import io
import uuid
from types import SimpleNamespace
from uuid import UUID

import pytest

from conftest import register_user

EICAR_STRING = (
    r"X5O!P%@AP[4\PZX54(P^)7CC)7}"
    r"$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
).encode("ascii")


def _make_pending_file(db_session, owner_id, content: bytes, name: str = "pytest_avscan.bin"):
    """Sube `content` directo al bucket privado (mismo mecanismo real que
    usa la app) y crea la fila `File` correspondiente con
    `scan_status='pending'` -- el punto de partida real que ve
    `scan_uploaded_file`. Devuelve el objeto `File` (ya con `db.refresh`)."""
    from app.files.models import File
    from app.files.service import upload_private_file

    storage_key = upload_private_file(f"files/{owner_id}", content, ".bin")

    file_obj = File(
        name=name,
        folder_id=None,
        owner_id=owner_id,
        storage_key=storage_key,
        size_bytes=len(content),
        mime_type="application/octet-stream",
        scan_status="pending",
    )
    db_session.add(file_obj)
    db_session.commit()
    db_session.refresh(file_obj)
    return file_obj


def _owner_id(client, db_session) -> UUID:
    from app.users.repository import user as user_repo

    creds = register_user(client)
    user = user_repo.get_by_email(db_session, creds["email"])
    assert user is not None
    return user.id


def _latest_notification(db_session, user_id):
    from app.notifications.models import Notification

    return (
        db_session.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .first()
    )


def _object_exists_private(key: str) -> bool:
    from app.files.service import object_exists_private

    return object_exists_private(key)


def _object_exists_quarantine(key: str) -> bool:
    from app.core.config import settings
    from app.files.service import _get_client
    from app.worker.tasks.av_scan import MINIO_QUARANTINE_BUCKET

    client = _get_client()
    try:
        client.head_object(Bucket=MINIO_QUARANTINE_BUCKET, Key=key)
        return True
    except Exception:
        return False


# ==================== Contenido limpio -> 'clean' ====================

def test_clean_content_marks_file_clean_and_notifies(client, db_session):
    from app.worker.tasks.av_scan import scan_uploaded_file

    owner_id = _owner_id(client, db_session)
    content = b"Contenido de prueba, sin ninguna firma de amenaza.\n" * 1000  # ~50KB, alcanza
    file_obj = _make_pending_file(db_session, owner_id, content, name=f"pytest_clean_{uuid.uuid4().hex[:8]}.bin")

    scan_uploaded_file(str(file_obj.id))

    db_session.refresh(file_obj)
    assert file_obj.scan_status == "clean"
    assert _object_exists_private(file_obj.storage_key) is True

    notif = _latest_notification(db_session, owner_id)
    assert notif is not None
    assert notif.severity == "success"
    assert file_obj.name in notif.message


# ==================== EICAR real -> cuarentena ====================

def test_eicar_content_gets_quarantined_for_real(client, db_session):
    from app.storage_quota.repository import user_storage_quota_repo
    from app.storage_quota.service import reserve_upload_bytes
    from app.worker.tasks.av_scan import scan_uploaded_file

    owner_id = _owner_id(client, db_session)
    file_obj = _make_pending_file(db_session, owner_id, EICAR_STRING, name=f"pytest_eicar_{uuid.uuid4().hex[:8]}.bin")
    original_key = file_obj.storage_key

    # Simula la reserva de cuota que hace el flujo real de subida grande
    # (`app/uploads/service.py`) ANTES de encolar el escaneo -- sin esto el
    # hallazgo de la revisión adversarial (fuga de cuota al poner en
    # cuarentena) no tendría nada real que liberar y el test no lo
    # detectaría.
    reserve_upload_bytes(db_session, owner_id, file_obj.size_bytes)
    quota_before = user_storage_quota_repo.get_by_user_id(db_session, owner_id).bytes_used
    assert quota_before == file_obj.size_bytes

    scan_uploaded_file(str(file_obj.id))

    db_session.refresh(file_obj)
    assert file_obj.scan_status == "infected"

    # El objeto se MOVIÓ -- ya no está en el bucket privado normal...
    assert _object_exists_private(original_key) is False
    # ...y SÍ está en cuarentena, con la MISMA key.
    assert _object_exists_quarantine(original_key) is True

    # La fila File se conserva (rastro auditable) -- nunca se borra.
    from app.files.repository import file_repo
    assert file_repo.get_for_scan_worker(db_session, file_obj.id) is not None

    notif = _latest_notification(db_session, owner_id)
    assert notif is not None
    assert notif.severity == "error"
    assert "seguridad" in notif.title.lower() or "remov" in notif.title.lower()

    # Hallazgo de la revisión adversarial (2026-09-22, MEDIO): la cuota
    # reservada para un archivo puesto en cuarentena quedaba contada para
    # siempre en bytes_used, sin ningún camino de recuperación. Confirma
    # que vuelve a su valor previo a la reserva (liberada por completo).
    db_session.expire_all()
    quota_after = user_storage_quota_repo.get_by_user_id(db_session, owner_id).bytes_used
    assert quota_after == 0


# ==================== Indexación de contenido tras 'clean' ====================

def test_clean_file_enqueues_content_indexing(client, db_session, monkeypatch):
    """Hallazgo de la revisión adversarial (2026-09-22, funcional): un
    archivo subido por el camino grande nunca quedaba buscable por
    contenido -- `scan_uploaded_file` ahora encola `index_file_content`
    (Ronda 6) en el mismo punto donde marca `scan_status='clean'`. No se
    espera acá a que el worker de indexing real procese el archivo (eso
    lo cubre `test_content_indexing.py`/la verificación en vivo) -- se
    confirma que la tarea CORRECTA se encoló, con los argumentos correctos
    (mismo contrato posicional que ya usa `app/files/router.py`)."""
    import app.worker.tasks.av_scan as av_scan

    calls = []
    monkeypatch.setattr(
        av_scan,
        "_enqueue_content_indexing",
        lambda file_obj: calls.append(file_obj.id),
    )

    owner_id = _owner_id(client, db_session)
    content = b"Contenido de prueba indexable, palabraunicaxyz789.\n" * 100
    file_obj = _make_pending_file(db_session, owner_id, content, name=f"pytest_idx_{uuid.uuid4().hex[:8]}.bin")

    av_scan.scan_uploaded_file(str(file_obj.id))

    db_session.refresh(file_obj)
    assert file_obj.scan_status == "clean"
    assert calls == [file_obj.id]


def test_enqueue_content_indexing_calls_real_task_with_correct_args(client, db_session, monkeypatch):
    """Prueba `_enqueue_content_indexing` en sí (no a través de
    `scan_uploaded_file`) -- confirma el contrato posicional real
    (`index_file_content.delay(tenant_schema, file_id_str)`, MISMO que
    `app/files/router.py::_enqueue_content_indexing`)."""
    import app.worker.tasks.av_scan as av_scan
    from app.worker.tasks.indexing import index_file_content

    owner_id = _owner_id(client, db_session)
    content = b"contenido chico, bien por debajo del tope de indexacion"
    file_obj = _make_pending_file(db_session, owner_id, content, name=f"pytest_idxcall_{uuid.uuid4().hex[:8]}.bin")

    calls = []
    monkeypatch.setattr(index_file_content, "delay", lambda *args: calls.append(args))

    av_scan._enqueue_content_indexing(file_obj)

    assert calls == [(None, str(file_obj.id))]


def test_large_file_over_indexing_cap_is_not_indexed(client, db_session, monkeypatch):
    """Un archivo por encima de `AV_SCAN_INDEXING_MAX_SIZE_BYTES` queda
    'clean' igual (usable, descargable) pero NO se encola para indexación
    -- `index_file_content` no fue diseñada para streaming (lee todo a
    memoria), encolarla sin tope para un archivo de varios GB reintroduciría
    el mismo problema de memoria que esta ronda existe para resolver."""
    import app.worker.tasks.av_scan as av_scan
    from app.worker.tasks.indexing import index_file_content

    owner_id = _owner_id(client, db_session)
    content = b"contenido chico en MinIO, el tamano declarado es lo que importa"
    file_obj = _make_pending_file(db_session, owner_id, content, name=f"pytest_idxbig_{uuid.uuid4().hex[:8]}.bin")
    # El contenido REAL en MinIO puede ser chico -- lo que decide el tope es
    # `size_bytes` de la fila `File` (mismo campo que usa la app real,
    # poblado con el tamaño real declarado/verificado por `app/uploads/`).
    file_obj.size_bytes = av_scan.AV_SCAN_INDEXING_MAX_SIZE_BYTES + 1
    db_session.commit()

    calls = []
    monkeypatch.setattr(index_file_content, "delay", lambda *args: calls.append(args))

    av_scan._enqueue_content_indexing(file_obj)

    assert calls == []


# ==================== clamd inalcanzable -> fail-closed ====================

class _RetrySignal(Exception):
    """Marca que el doble liviano de la tarea (`_FakeTask`) usa para señalar
    que `self.retry(...)` fue invocado -- nunca se deja escapar de un test
    sin capturarla explícitamente."""
    def __init__(self, exc, countdown):
        self.exc = exc
        self.countdown = countdown


class _FakeTask:
    """Doble liviano de una instancia de tarea Celery `bind=True` -- expone
    solo lo que `_handle_scan_infra_error` necesita (`self.request.retries`
    y `self.retry(...)`), sin pasar por el broker real. Permite probar la
    lógica de "reintentar N veces, después fail-closed a scan_failed" de
    forma determinística, sin depender de countdowns reales de minutos."""
    def __init__(self, retries: int):
        self.request = SimpleNamespace(retries=retries)

    def retry(self, exc=None, countdown=None):
        raise _RetrySignal(exc, countdown)


def test_clamd_unreachable_retries_then_fails_closed_without_ever_marking_clean(client, db_session):
    import app.worker.tasks.av_scan as av_scan

    owner_id = _owner_id(client, db_session)
    file_obj = _make_pending_file(db_session, owner_id, b"contenido cualquiera", name=f"pytest_clamdown_{uuid.uuid4().hex[:8]}.bin")

    # Este test ejercita `_handle_scan_infra_error` DIRECTO (no el escaneo
    # real de punta a punta) -- ver docstring de `_FakeTask`: monkeypatchear
    # `scan_minio_object_for_malware` acá sería inútil, `scan_uploaded_file`
    # lo importa de forma diferida dentro de la propia función (mismo
    # criterio del resto del proyecto), así que no queda como atributo de
    # módulo para pisar.

    # Intentos por debajo del máximo -- debe pedir retry, NUNCA tocar
    # scan_status (fail-closed real: sigue 'pending', no 'clean').
    for attempt in range(av_scan.AV_SCAN_MAX_ERROR_RETRIES):
        fake_task = _FakeTask(retries=attempt)
        with pytest.raises(_RetrySignal):
            av_scan._handle_scan_infra_error(fake_task, db_session, file_obj, ConnectionError("x"))
        db_session.refresh(file_obj)
        assert file_obj.scan_status == "pending"

    # Reintentos agotados -- fail-closed a 'scan_failed', NUNCA 'clean'.
    fake_task = _FakeTask(retries=av_scan.AV_SCAN_MAX_ERROR_RETRIES)
    av_scan._handle_scan_infra_error(fake_task, db_session, file_obj, ConnectionError("clamd sigue caído"))

    db_session.refresh(file_obj)
    assert file_obj.scan_status == "scan_failed"
    assert file_obj.scan_status != "clean"

    notif = _latest_notification(db_session, owner_id)
    assert notif is not None
    assert notif.severity == "error"


# ==================== Límite de concurrencia (semáforo Redis) ====================

def test_concurrency_semaphore_enforces_limit_and_requeues(client, db_session, monkeypatch):
    """No corre `AV_SCAN_CONCURRENCY_LIMIT + 1` escaneos reales en paralelo
    (lento e innecesario) -- en cambio, prueba el semáforo Redis en sí
    (`_try_acquire_scan_slot`/`_release_scan_slot`, el mecanismo real que
    usa la tarea) más la tarea completa con el cupo YA agotado, confirmando
    que se reencola (`apply_async`) en vez de escanear."""
    import app.worker.tasks.av_scan as av_scan

    redis_client = av_scan._get_redis_client()
    if redis_client is None:
        pytest.skip("Redis no disponible en este entorno de test")

    redis_client.delete(av_scan._SEMAPHORE_KEY)
    try:
        acquired = []
        for _ in range(av_scan.AV_SCAN_CONCURRENCY_LIMIT):
            ok = av_scan._try_acquire_scan_slot()
            assert ok is True
            acquired.append(ok)

        # Un cupo más allá del límite -- debe fallar.
        assert av_scan._try_acquire_scan_slot() is False

        # Liberar uno -- vuelve a haber cupo.
        av_scan._release_scan_slot()
        assert av_scan._try_acquire_scan_slot() is True

        # Limpieza -- liberar todos los cupos que quedaron tomados.
        for _ in range(av_scan.AV_SCAN_CONCURRENCY_LIMIT):
            av_scan._release_scan_slot()
    finally:
        redis_client.delete(av_scan._SEMAPHORE_KEY)

    # --- Ahora, con el cupo lleno, la tarea completa debe reencolar sin escanear ---
    owner_id = _owner_id(client, db_session)
    file_obj = _make_pending_file(db_session, owner_id, b"contenido", name=f"pytest_concurrency_{uuid.uuid4().hex[:8]}.bin")

    redis_client.delete(av_scan._SEMAPHORE_KEY)
    redis_client.set(av_scan._SEMAPHORE_KEY, av_scan.AV_SCAN_CONCURRENCY_LIMIT)

    requeued_calls = []

    def _fake_apply_async(args, countdown):
        requeued_calls.append((args, countdown))

    monkeypatch.setattr(av_scan.scan_uploaded_file, "apply_async", _fake_apply_async)

    try:
        av_scan.scan_uploaded_file(str(file_obj.id))
    finally:
        redis_client.delete(av_scan._SEMAPHORE_KEY)

    assert len(requeued_calls) == 1
    assert requeued_calls[0][0] == [str(file_obj.id)]
    assert requeued_calls[0][1] == av_scan.AV_SCAN_REQUEUE_COUNTDOWN_SECONDS

    # Nunca llegó a escanear -- sigue 'pending'.
    db_session.refresh(file_obj)
    assert file_obj.scan_status == "pending"
