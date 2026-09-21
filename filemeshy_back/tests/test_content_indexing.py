"""Ronda 6 -- búsqueda por contenido de archivo (Parte 1: texto plano y
Office moderno, sin depender de Tesseract/OCR -- eso lo cubre
`test_ocr_extraction.py`).

La tarea de indexación (`app.worker.tasks.indexing.index_file_content`) se
invoca ADEMÁS directo como función Python normal, síncrona, sin pasar por
el broker real de Celery -- mismo patrón que ya usa
`tests/test_purge_file_versions_quota.py` para
`purge_deleted_files_and_folders`. Es "además" y no "en vez de" a propósito:
el propio `upload_file`/`upload_file_version`/etc. YA encola la tarea real
con `.delay()` (ver `_enqueue_content_indexing` en el router), así que
contra el stack completo (con `celery_worker` real consumiendo la cola
`indexing`) el archivo puede quedar indexado casi al instante para un .txt
chico -- ANTES de que este test llegue a llamar `_index_now`. Por eso
ningún test de este archivo afirma un estado "todavía sin indexar" como
aserción dura (sería una carrera imposible de ganar contra un worker de
verdad, confirmado en vivo: 2 tests fallaban así corriendo contra el stack
real con Redis/Celery de punta a punta) -- la llamada síncrona a
`_index_now` sigue estando para GARANTIZAR que, para cuando se busca, la
indexación YA terminó, sin importar si hay o no un worker real corriendo en
paralelo (upsert idempotente -- no importa si el worker real y esta llamada
directa procesan el mismo archivo dos veces, el resultado final converge).
`tenant_schema` se pasa `None` (este stack corre en `DEPLOYMENT_MODE=local`,
sin multi-tenant real, ver `app/worker/db.py::get_worker_db`)."""
import io
import time

from conftest import auth_headers, login_user, register_user

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _register_login(client):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    return creds, token


def _upload(client, token, content: bytes, filename: str, mime: str) -> dict:
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), mime)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _index_now(file_id: str) -> None:
    """Corre la extracción de contenido de `file_id` de forma síncrona,
    directo en el proceso de test (sin Celery/broker real)."""
    from app.worker.tasks.indexing import index_file_content

    index_file_content(None, file_id)


def _search(client, token, q: str) -> list:
    resp = client.get("/files", headers=auth_headers(token), params={"q": q})
    assert resp.status_code == 200, resp.text
    return resp.json()["files"]


def _wait_for_index_status(client, token, file_id: str, *, timeout: float = 5.0, interval: float = 0.2) -> dict:
    """Poll de `GET /files/{id}/index-status` hasta que salga de 'pending'
    (terminal: 'done'/'failed'/'unsupported') o venza `timeout` -- nunca
    asume cuánto tarda un worker real (puede ser casi instantáneo para un
    .txt chico, o no haber corrido todavía). Devuelve el último body leído,
    terminal o no (el caller decide qué hacer si venció el timeout)."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        resp = client.get(f"/files/{file_id}/index-status", headers=auth_headers(token))
        assert resp.status_code == 200, resp.text
        last = resp.json()
        if last["status"] != "pending":
            return last
        time.sleep(interval)
    return last


# ==================== Texto plano ====================

def test_txt_file_found_by_content_word_not_in_name(client):
    """Palabra única SOLO en el contenido (nunca en el nombre del archivo) --
    antes de esta ronda, `CRUDFile.search` solo miraba `File.name.ilike`, así
    que este archivo era invisible para esa búsqueda.

    NO se afirma un estado "todavía sin indexar" antes de esto -- contra un
    worker Celery real, la tarea encolada por el propio `upload_file` puede
    terminar de procesar este .txt chico casi al instante, antes incluso de
    que el test llegue a esta línea (carrera real, confirmada corriendo
    contra el stack completo con Redis/`celery_worker` de verdad). Lo único
    que este test garantiza -- vía `_index_now`, síncrono e idempotente -- es
    que para cuando busca, la indexación YA terminó, sin importar si un
    worker real la procesó también en paralelo."""
    _, token = _register_login(client)

    unique_word = "xylophonemarker7742"
    content = f"Este documento habla de un {unique_word} muy particular.".encode("utf-8")
    uploaded = _upload(client, token, content, "pytest_reporte_ventas.txt", "text/plain")

    _index_now(uploaded["id"])

    results = _search(client, token, unique_word)
    names = [f["name"] for f in results]
    assert uploaded["name"] in names, f"El archivo no apareció buscando por contenido: {results}"

    matched = next(f for f in results if f["id"] == uploaded["id"])
    assert matched["matched_by"] == "content"

    # Control negativo -- palabra que no está ni en nombre ni en
    # contenido no debería devolver el archivo.
    assert uploaded["name"] not in [f["name"] for f in _search(client, token, "palabraqueseguronoexiste999")]


def test_txt_file_found_by_name_still_works_matched_by_name(client):
    """Regresión -- la búsqueda por NOMBRE (comportamiento pre-Ronda-6) sigue
    funcionando igual, con `matched_by='name'` cuando el archivo no tiene
    (todavía) contenido indexado."""
    _, token = _register_login(client)

    uploaded = _upload(
        client, token, b"contenido sin relacion", "pytest_facturaunica123.txt", "text/plain"
    )
    # Sin indexar a propósito -- confirma que la búsqueda por nombre no
    # depende de que exista una fila en file_content_index.
    results = _search(client, token, "facturaunica123")
    names = [f["name"] for f in results]
    assert uploaded["name"] in names
    matched = next(f for f in results if f["id"] == uploaded["id"])
    assert matched["matched_by"] == "name"


def test_docx_file_found_by_content_word_not_in_name(client):
    """Mismo caso que el .txt pero con un .docx real generado con
    `python-docx` -- ejercita `_extract_docx_text` de la tarea de
    indexación de punta a punta (subida real -> MinIO -> extracción ->
    búsqueda)."""
    import docx

    _, token = _register_login(client)

    unique_word = "quetzalcoatl99887"
    buf = io.BytesIO()
    document = docx.Document()
    document.add_paragraph(f"Reporte interno: mencionar {unique_word} en la reunión de mañana.")
    document.save(buf)
    content = buf.getvalue()

    uploaded = _upload(client, token, content, "pytest_documento_generico.docx", DOCX_MIME)
    _index_now(uploaded["id"])

    results = _search(client, token, unique_word)
    names = [f["name"] for f in results]
    assert uploaded["name"] in names, f"El .docx no apareció buscando por contenido: {results}"
    matched = next(f for f in results if f["id"] == uploaded["id"])
    assert matched["matched_by"] == "content"


def test_index_status_endpoint_reflects_extraction(client):
    """`GET /files/{id}/index-status` -- termina en 'done' tras indexar.

    El estado INMEDIATAMENTE después del upload puede ser 'pending' (sin
    worker real corriendo, o si el worker real todavía no llegó a esta
    tarea puntual) O YA 'done' (si un worker real la procesó casi al
    instante -- típico para un .txt chico contra el stack completo,
    confirmado en vivo) -- no se afirma cuál de los dos es, sería una
    carrera imposible de garantizar contra un worker de verdad. Lo que SÍ
    es un contrato firme: el estado FINAL, una vez que la indexación
    terminó (forzada acá vía `_index_now`, síncrona e idempotente), tiene
    que ser 'done' con `indexed_at` seteado -- se confirma con un poll corto
    en vez de asumir que un único GET inmediatamente después alcanza."""
    _, token = _register_login(client)

    uploaded = _upload(client, token, b"contenido cualquiera", "pytest_status.txt", "text/plain")

    initial = client.get(f"/files/{uploaded['id']}/index-status", headers=auth_headers(token))
    assert initial.status_code == 200, initial.text
    assert initial.json()["status"] in ("pending", "done")
    if initial.json()["status"] == "pending":
        assert initial.json()["indexed_at"] is None

    _index_now(uploaded["id"])

    final_status = _wait_for_index_status(client, token, uploaded["id"])
    assert final_status["status"] == "done", final_status
    assert final_status["indexed_at"] is not None


def test_new_version_reindexes_content(client):
    """Subir una versión NUEVA reemplaza el contenido indexado -- una palabra
    que solo estaba en la versión VIEJA deja de matchear después de indexar
    la versión nueva (mismo criterio que `FileContentIndex.upsert`: relación
    1:1, siempre refleja la extracción MÁS RECIENTE)."""
    _, token = _register_login(client)

    old_word = "murcielagorojo321"
    new_word = "elefanteazul654"

    uploaded = _upload(
        client, token, f"version vieja con {old_word}".encode(), "pytest_versionado.txt", "text/plain"
    )
    _index_now(uploaded["id"])
    assert uploaded["name"] in [f["name"] for f in _search(client, token, old_word)]

    version_resp = client.post(
        f"/files/{uploaded['id']}/versions",
        headers=auth_headers(token),
        files={
            "file": (
                "pytest_versionado_v2.txt",
                io.BytesIO(f"version nueva con {new_word}".encode()),
                "text/plain",
            )
        },
    )
    assert version_resp.status_code == 201, version_resp.text
    _index_now(uploaded["id"])

    assert uploaded["name"] in [f["name"] for f in _search(client, token, new_word)]
    assert uploaded["name"] not in [f["name"] for f in _search(client, token, old_word)]
