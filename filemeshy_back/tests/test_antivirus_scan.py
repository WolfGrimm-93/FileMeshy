"""Ronda 7 -- antivirus: escaneo de malware (ClamAV) de todo contenido nuevo
ANTES de subirlo a MinIO.

Política fail-closed (ver `app.files.router._scan_for_malware_or_raise` y
`app.files.service.scan_for_malware`):
- Infectado -> 422, nunca se sube nada a MinIO ni se crea fila en BD.
- `clamd` no responde -> 503, tampoco se sube nada -- NUNCA se asume "está
  limpio" en silencio solo porque el antivirus no contestó.

Dos estilos de test, mismo criterio que `test_preview_office.py`:

1. Contra el `clamav` REAL ya levantado en este stack (sin mocks) -- el
   string EICAR estándar de la industria (detectado como amenaza de prueba
   por cualquier motor de antivirus real, sin ser malware de verdad) y un
   archivo de texto limpio. Si el contenedor `clamav` deja de estar arriba
   en una corrida futura, estos son los tests que van a fallar primero.

2. `clamd` caído/no disponible, simulado con `monkeypatch` sobre
   `app.files.router.scan_for_malware` (sin tirar abajo el contenedor real)
   -- determinista, no depende de infraestructura.

El helper de escaneo (`_scan_for_malware_or_raise`) está enganchado en UN
SOLO lugar por camino de subida: `_validate_and_store_upload` (cubre
`upload_file` y `upload_file_via_share`) y `_create_new_file_version` (cubre
`upload_file_version` y `replace_file_via_share`) -- este archivo ejercita
`upload_file` y `upload_file_version` (uno de cada helper compartido), que
alcanza para confirmar que el enganche funciona en los dos puntos sin
duplicar cobertura de los 4 endpoints uno por uno.
"""
import asyncio
import io
import socket
import threading
import time
import uuid
from uuid import UUID

import pytest
from starlette.datastructures import Headers

from conftest import auth_headers, login_user, register_user

# String EICAR estándar de la industria (https://www.eicar.org/) -- cualquier
# motor de antivirus real lo marca como amenaza de prueba, nunca malware de
# verdad. Se arma concatenando en runtime (nunca como literal completo en el
# código fuente) para que un antivirus que escanee este propio repo no lo
# marque a él mismo.
EICAR_STRING = (
    r"X5O!P%@AP[4\PZX54(P^)7CC)7}"
    r"$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
).encode("ascii")


def _register_login(client):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    return creds, token


def _upload(client, token, content: bytes, filename: str):
    return client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )


def _upload_version(client, token, file_id, content: bytes, filename: str):
    return client.post(
        f"/files/{file_id}/versions",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )


def _my_quota_bytes_used(client, token) -> int:
    resp = client.get("/storage-quotas/me", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["bytes_used"]


def _get_user(db_session, email):
    from app.users.repository import user as user_repo

    user = user_repo.get_by_email(db_session, email)
    assert user is not None
    return user


def _get_file_row(db_session, file_id: str):
    from app.files.repository import file_repo

    file_row = file_repo.get(db_session, UUID(file_id))
    assert file_row is not None
    return file_row


def _make_upload_file(content: bytes, filename: str, content_type: str = "text/plain"):
    """Construye un `UploadFile` real (no un mock) para llamar los endpoints
    ASYNC del router DIRECTO en proceso -- necesario para los tests de
    `clamd` caído: el `client` HTTP le pega a un proceso `uvicorn` SEPARADO
    (ver docstring de `conftest.py`), así que `monkeypatch` sobre
    `app.files.router.scan_for_malware` no tiene ningún efecto ahí (no es el
    mismo proceso/módulo cargado). Mismo patrón que usa
    `test_preview_office.py` para `get_file_preview` (sync) -- acá se aplica
    a `upload_file`/`upload_file_version`, que son `async def`, corridos con
    `asyncio.run`."""
    from fastapi import UploadFile

    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def _file_row_exists(db_session, owner_email: str, filename: str) -> bool:
    """Confirma directo en Postgres si existe (o no) una fila `File` con ese
    nombre para el dueño de `owner_email` -- el test necesita verificar la
    AUSENCIA de la fila (fail-closed real), no solo el código de status de
    la response."""
    from sqlalchemy import text

    row = db_session.execute(
        text(
            "SELECT COUNT(*) FROM files f "
            "JOIN users u ON u.id = f.owner_id "
            "WHERE u.email = :email AND f.name = :name"
        ),
        {"email": owner_email, "name": filename},
    ).first()
    return row[0] > 0


# ==================== EICAR real contra clamd real ====================

def test_upload_with_eicar_content_is_rejected_and_never_persisted(client, db_session):
    """Subir un archivo cuyo CONTENIDO real es el string EICAR -> 422 con
    mensaje claro, y el archivo NUNCA queda en MinIO ni en la BD (fila
    `File` no creada, cuota no consumida)."""
    creds, token = _register_login(client)
    filename = f"pytest_eicar_{uuid.uuid4().hex[:8]}.txt"

    bytes_used_before = _my_quota_bytes_used(client, token)

    resp = _upload(client, token, EICAR_STRING, filename)

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "malicioso" in detail.lower()
    assert "eicar" in detail.lower()

    # Nunca se creó la fila File para este archivo.
    assert _file_row_exists(db_session, creds["email"], filename) is False

    # La cuota del usuario no se movió -- el escaneo corre ANTES de reservar
    # cuota, así que un archivo rechazado no debe dejar rastro ahí tampoco.
    bytes_used_after = _my_quota_bytes_used(client, token)
    assert bytes_used_after == bytes_used_before


def test_upload_clean_file_succeeds_through_real_clamav(client):
    """Un archivo de texto real, sin ninguna firma de amenaza, sube sin
    problema -- confirma que el escaneo no da falsos positivos con
    contenido inocuo ni bloquea el camino feliz."""
    _, token = _register_login(client)
    filename = f"pytest_clean_{uuid.uuid4().hex[:8]}.txt"
    content = b"Este es un archivo de texto perfectamente normal y sin malware.\n"

    resp = _upload(client, token, content, filename)

    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == filename
    assert resp.json()["size_bytes"] == len(content)


def test_upload_new_version_with_eicar_is_rejected_and_no_version_created(client, db_session):
    """Mismo criterio que la subida inicial, pero en el OTRO helper
    compartido (`_create_new_file_version`, vía `POST /files/{id}/versions`)
    -- confirma que el enganche del escaneo cubre también el camino de
    versionado (Ronda 4), no solo la subida inicial."""
    creds, token = _register_login(client)
    filename = f"pytest_version_clean_{uuid.uuid4().hex[:8]}.txt"

    upload_resp = _upload(client, token, b"contenido original limpio", filename)
    assert upload_resp.status_code == 201, upload_resp.text
    file_obj = upload_resp.json()

    bytes_used_before = _my_quota_bytes_used(client, token)

    version_resp = _upload_version(
        client, token, file_obj["id"], EICAR_STRING, f"pytest_v2_eicar_{uuid.uuid4().hex[:8]}.txt"
    )

    assert version_resp.status_code == 422, version_resp.text
    detail = version_resp.json()["detail"]
    assert "malicioso" in detail.lower()
    assert "eicar" in detail.lower()

    # Sigue habiendo una sola versión (la original) -- la versión con EICAR
    # nunca se creó.
    versions_resp = client.get(f"/files/{file_obj['id']}/versions", headers=auth_headers(token))
    assert versions_resp.status_code == 200, versions_resp.text
    assert len(versions_resp.json()) == 1

    # Cuota tampoco se movió por el intento rechazado.
    bytes_used_after = _my_quota_bytes_used(client, token)
    assert bytes_used_after == bytes_used_before


# ==================== clamd caído -- simulado con monkeypatch ====================

def test_upload_rejects_with_503_when_clamav_is_unreachable(client, db_session, monkeypatch):
    """Si `clamd` no responde (conexión rechazada/timeout/lo que sea), la
    política es fail-closed: 503, y el archivo NUNCA se sube -- nunca se
    asume "está limpio" en silencio solo porque el antivirus no contestó.

    Llama `upload_file` DIRECTO en proceso (no por HTTP) -- el `client` le
    pega a un `uvicorn` en un proceso SEPARADO, así que `monkeypatch` sobre
    `app.files.router.scan_for_malware` no le llegaría (ver
    `_make_upload_file`)."""
    from fastapi import HTTPException

    from app.files.router import upload_file

    creds, token = _register_login(client)
    filename = f"pytest_clamdown_{uuid.uuid4().hex[:8]}.txt"

    def fake_scan_raises(content: bytes):
        raise ConnectionError("simulado: clamd no responde (test)")

    monkeypatch.setattr("app.files.router.scan_for_malware", fake_scan_raises)

    user = _get_user(db_session, creds["email"])
    upload = _make_upload_file(b"contenido totalmente inocuo", filename)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(upload_file(file=upload, folder_id=None, db=db_session, current_user=user))

    assert exc_info.value.status_code == 503
    assert "no disponible" in exc_info.value.detail.lower()
    assert _file_row_exists(db_session, creds["email"], filename) is False


def test_upload_new_version_rejects_with_503_when_clamav_is_unreachable(client, db_session, monkeypatch):
    """Mismo escenario de `clamd` caído, pero en el helper de versiones
    (`_create_new_file_version`) -- confirma que el fail-closed aplica
    también ahí, no solo en la subida inicial. Subida inicial por HTTP real
    (camino feliz, sin mock); el intento de versión nueva con `clamd` caído
    se llama en proceso, mismo motivo que el test anterior."""
    from fastapi import HTTPException

    from app.files.router import upload_file_version

    creds, token = _register_login(client)
    filename = f"pytest_version_clamdown_{uuid.uuid4().hex[:8]}.txt"

    upload_resp = _upload(client, token, b"contenido original", filename)
    assert upload_resp.status_code == 201, upload_resp.text
    file_obj = upload_resp.json()

    def fake_scan_raises(content: bytes):
        raise ConnectionError("simulado: clamd no responde (test)")

    monkeypatch.setattr("app.files.router.scan_for_malware", fake_scan_raises)

    user = _get_user(db_session, creds["email"])
    file_row = _get_file_row(db_session, file_obj["id"])
    upload = _make_upload_file(
        b"contenido de la v2, nunca deberia subirse",
        f"pytest_v2_clamdown_{uuid.uuid4().hex[:8]}.txt",
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(upload_file_version(file_id=file_row.id, file=upload, db=db_session, current_user=user))

    assert exc_info.value.status_code == 503
    assert "no disponible" in exc_info.value.detail.lower()

    # Sigue habiendo una sola versión -- el intento con clamd caído nunca
    # llegó a crear la v2.
    versions_resp = client.get(f"/files/{file_obj['id']}/versions", headers=auth_headers(token))
    assert versions_resp.status_code == 200, versions_resp.text
    assert len(versions_resp.json()) == 1


# ==================== Hallazgos de la revisión adversarial (Ronda 7) ====================
# Dos hallazgos MEDIUM reales sobre la implementación original, reproducidos
# en vivo contra `clamav` real por el equipo de revisión:
#
# 1. `scan_for_malware` es bloqueante de verdad (sockets crudos) y se
#    llamaba directo desde las corutinas `async def` de los endpoints --
#    sin `run_in_threadpool`, el escaneo de UN upload congelaba el loop de
#    asyncio ENTERO, afectando a TODOS los usuarios concurrentes (no solo
#    al que subía). Fix: `_scan_for_malware_or_raise` ahora es `async` y
#    corre `scan_for_malware` vía `run_in_threadpool` (ver router.py).
#
# 2. `sock.settimeout(timeout)` es un timeout de INACTIVIDAD por syscall,
#    se resetea en cada `send`/`recv` -- un peer que responde a los tumbos
#    (bytes sueltos, cada intervalo por debajo del timeout) podía estirar
#    la conexión varias veces el timeout "documentado" sin disparar nunca
#    un `socket.timeout`. Fix: deadline TOTAL real dentro de
#    `scan_for_malware`, recalculando el tiempo remanente antes de cada
#    syscall (ver `_ScanDeadlineExceeded` en service.py).
#
# Los dos tests de abajo usan un servidor TCP real "a los tumbos" (mismo
# tipo de servidor fake que usó la revisión para reproducir el hallazgo 2)
# -- nada mockeado a nivel de protocolo, solo la infraestructura (no hace
# falta tirar abajo `clamav` real para esto).

def _start_dribbling_fake_clamd(byte_interval: float = 0.4):
    """Servidor TCP real que acepta UNA conexión y devuelve una respuesta
    parcial ("stream: OK", sin el NUL final que cierra un mensaje INSTREAM
    válido) UN BYTE A LA VEZ, con una pausa de `byte_interval` segundos
    entre cada uno -- nunca dispara `socket.timeout` en un `recv()`
    individual mientras `byte_interval` sea menor al timeout configurado
    por el test, así que la única forma de cortar la conexión es un
    deadline TOTAL real (hallazgo 2) o el propio cierre del socket cliente.

    Corre en un thread daemon -- termina solo cuando el lado cliente
    cierra la conexión (el `sendall` del server empieza a fallar) o cuando
    el proceso de test termina."""
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]

    def _serve():
        try:
            conn, _ = server_sock.accept()
        except OSError:
            return
        try:
            payload = b"stream: OK"
            while True:
                for byte in payload:
                    try:
                        conn.sendall(bytes([byte]))
                    except OSError:
                        return
                    time.sleep(byte_interval)
        finally:
            conn.close()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    return server_sock, port


def test_scan_for_malware_enforces_total_deadline_not_just_per_syscall_timeout(monkeypatch):
    """Hallazgo 2 -- regresión: sin un deadline TOTAL real, un peer que
    responde a los tumbos podía estirar el escaneo varias veces el timeout
    configurado (reproducido por la revisión: timeout=2s -> 15s reales,
    7.5x). Con el fix, `scan_for_malware` debe cortar CERCA del timeout
    configurado, no muy por encima."""
    from app.core.config import settings as app_settings
    from app.files.service import scan_for_malware

    server_sock, port = _start_dribbling_fake_clamd(byte_interval=0.4)
    try:
        timeout = 1.5
        monkeypatch.setattr(app_settings, "CLAMAV_HOST", "127.0.0.1")
        monkeypatch.setattr(app_settings, "CLAMAV_PORT", port)
        monkeypatch.setattr(app_settings, "CLAMAV_SCAN_TIMEOUT_SECONDS", timeout)

        start = time.monotonic()
        with pytest.raises(ConnectionError):
            scan_for_malware(b"contenido de prueba, no importa el tamano")
        elapsed = time.monotonic() - start

        assert elapsed < timeout * 2, (
            f"scan_for_malware tardó {elapsed:.2f}s con timeout configurado de "
            f"{timeout}s -- el deadline TOTAL no está cortando a tiempo (antes "
            "del fix esto se estiraba varios múltiplos del timeout)."
        )
        assert elapsed >= timeout * 0.5, (
            "cortó sospechosamente rápido -- puede que ni siquiera haya "
            "llegado a usar el presupuesto de tiempo configurado."
        )
    finally:
        server_sock.close()


async def _tick_counter(duration: float, interval: float = 0.05) -> int:
    """Cuenta cuántas veces logra 'tickear' una tarea liviana de asyncio
    durante `duration` segundos -- usada como testigo de que el loop de
    asyncio sigue vivo y atendiendo otras corutinas mientras algo más
    corre en paralelo."""
    ticks = 0
    start = time.monotonic()
    while time.monotonic() - start < duration:
        await asyncio.sleep(interval)
        ticks += 1
    return ticks


def test_malware_scan_runs_in_threadpool_and_does_not_block_event_loop(monkeypatch):
    """Hallazgo 1 -- regresión: `scan_for_malware` es bloqueante (sockets
    crudos). Si `_scan_for_malware_or_raise` lo llamara directo (sin
    `run_in_threadpool`), la corutina nunca cedería el control mientras
    dura el escaneo -- una tarea concurrente liviana (`_tick_counter`) NO
    podría arrancar hasta que el escaneo termine del todo, así que el
    tiempo total de correr las dos cosas "en paralelo" (`asyncio.gather`)
    sería la SUMA de ambas duraciones, no el máximo.

    Con el fix (`run_in_threadpool`), las dos corren de verdad en paralelo
    -- el tiempo total debe acercarse al máximo de las dos duraciones
    (~`scan_timeout`), nunca a la suma (~2x `scan_timeout`)."""
    from fastapi import HTTPException

    from app.files.router import _scan_for_malware_or_raise

    server_sock, port = _start_dribbling_fake_clamd(byte_interval=0.4)
    try:
        scan_timeout = 1.5
        from app.core.config import settings as app_settings

        monkeypatch.setattr(app_settings, "CLAMAV_HOST", "127.0.0.1")
        monkeypatch.setattr(app_settings, "CLAMAV_PORT", port)
        monkeypatch.setattr(app_settings, "CLAMAV_SCAN_TIMEOUT_SECONDS", scan_timeout)

        async def _run_scan():
            with pytest.raises(HTTPException):
                await _scan_for_malware_or_raise(b"contenido de prueba", original_name="x.txt")

        async def scenario():
            start = time.monotonic()
            await asyncio.gather(_run_scan(), _tick_counter(scan_timeout))
            return time.monotonic() - start

        elapsed = asyncio.run(scenario())

        assert elapsed < scan_timeout * 1.6, (
            f"El escaneo parece estar bloqueando el loop de asyncio: correr el "
            f"escaneo junto a una tarea liviana de {scan_timeout}s tardó "
            f"{elapsed:.2f}s en total -- deberían solaparse (correr en "
            f"threadpool), no sumarse (bloquear el loop)."
        )
    finally:
        server_sock.close()
