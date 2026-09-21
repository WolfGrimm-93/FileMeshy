"""Ronda 5 -- preview extendido, Parte 2: documentos Office vía el
conversor aislado `office_converter` (servicio Docker nuevo, construido en
paralelo por otro agente de esta misma ronda -- ver
`filemeshy_office_converter/`).

El contrato asumido (`POST http://office_converter:8080/convert`, multipart
campo "file", 200 -> bytes de PDF, error -> JSON `{"detail": ...}`) se
confirmó EXACTO contra `filemeshy_office_converter/server.py` -- ver
`GET /files/{id}/preview` en `app/files/router.py` y `convert_office_to_pdf`
en `app/files/service.py`.

Dos estilos de test conviven acá a propósito:

1. Contra el servidor REAL (fixture `client`, HTTP de verdad), incluido un
   smoke test de integración genuino de punta a punta: el contenedor
   `office_converter` se levantó durante esta misma ronda (en paralelo, por
   el otro agente) y ya responde en este stack -- `test_preview_of_office_file_converts_for_real_and_caches`
   sube un archivo, pide el preview SIN mockear nada, y confirma que el
   backend recibe un PDF real convertido de verdad y lo cachea en MinIO. Si
   ese contenedor deja de estar arriba en una corrida futura (se apagó, se
   está reconstruyendo, etc.), ESE es el test que va a fallar primero -- la
   lógica de caching/errores en sí sigue cubierta de forma determinista,
   sin depender de la disponibilidad real del servicio, por los tests de
   abajo con `monkeypatch`.

2. Llamando la función de la ruta DIRECTO en proceso (no por HTTP) con
   `monkeypatch` sobre `app.files.router.convert_office_to_pdf` para los
   caminos de ÉXITO+CACHÉ, ERROR, e INVALIDACIÓN POR VERSIÓN NUEVA -- estos
   NO dependen de que `office_converter` esté arriba (deterministas). Es
   seguro llamar `get_file_preview(...)` como función Python normal: los
   decoradores de `APIRouter` no envuelven la función, solo la registran
   (mismo patrón que usa FastAPI internamente para tests unitarios de
   rutas). La sesión de PostgreSQL real (fixture `db_session`) y el MinIO
   real ya levantado SÍ se ejercitan de verdad -- solo la llamada HTTP al
   conversor es un stub en estos casos.
"""
import io
from uuid import UUID

import pytest

from conftest import auth_headers, login_user, register_user

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
LEGACY_DOC_MIME = "application/msword"


def _register_login(client):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    return creds, token


def _upload_with_mime(client, token, content: bytes, filename: str, mime: str) -> dict:
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), mime)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


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


# ==================== Contrato de mime types Office ====================

def test_office_mime_types_include_modern_and_legacy_formats():
    """Confirma el alcance pedido: docx/xlsx/pptx modernos + doc/xls/ppt
    legacy, todos ruteados por el mismo camino de conversión."""
    from app.files.router import OFFICE_MIME_TYPES

    assert DOCX_MIME in OFFICE_MIME_TYPES
    assert XLSX_MIME in OFFICE_MIME_TYPES
    assert "application/vnd.openxmlformats-officedocument.presentationml.presentation" in OFFICE_MIME_TYPES
    assert LEGACY_DOC_MIME in OFFICE_MIME_TYPES
    assert "application/vnd.ms-excel" in OFFICE_MIME_TYPES
    assert "application/vnd.ms-powerpoint" in OFFICE_MIME_TYPES


# ==================== Integración real de punta a punta ====================

def test_preview_of_office_file_converts_for_real_and_caches(client):
    """Smoke test de integración SIN mocks: `office_converter` está arriba
    en este stack -- confirma que el backend le pega de verdad, recibe un
    PDF real, y lo sirve cacheado desde una key determinista
    (`previews/{file_id}/{version_number}.pdf`, ver `office_preview_key`).

    Timeout generoso (LibreOffice headless arrancando en frío puede tardar
    varios segundos la primera vez) -- bien por debajo de los 35s que
    tolera la llamada interna real del backend al conversor."""
    _, token = _register_login(client)
    file_obj = _upload_with_mime(client, token, b"contenido de un docx de prueba real", "pytest_real.docx", DOCX_MIME)
    assert file_obj["mime_type"] == DOCX_MIME

    resp = client.get(f"/files/{file_obj['id']}/preview", headers=auth_headers(token), timeout=40.0)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mime_type"] == "application/pdf"
    assert f"previews/{file_obj['id']}/1.pdf" in body["preview_url"]

    # Segunda llamada -- misma key determinista de cache (versión sigue
    # siendo la 1, no se subió ninguna nueva).
    resp_2 = client.get(f"/files/{file_obj['id']}/preview", headers=auth_headers(token), timeout=40.0)
    assert resp_2.status_code == 200, resp_2.text
    assert f"previews/{file_obj['id']}/1.pdf" in resp_2.json()["preview_url"]


def test_preview_endpoint_requires_ownership(client):
    """Mismo criterio anti-IDOR que el resto del módulo -- IDOR sobre el
    endpoint nuevo, no solo sobre download/versions."""
    _, token_a = _register_login(client)
    _, token_b = _register_login(client)

    file_obj = _upload_with_mime(client, token_a, b"contenido privado de A", "pytest_a.docx", DOCX_MIME)

    resp = client.get(f"/files/{file_obj['id']}/preview", headers=auth_headers(token_b))
    assert resp.status_code == 404, resp.text


# ==================== Tipos ya servibles inline -- sin conversión ====================

def test_preview_of_plain_file_reuses_normal_download_url(client):
    """Un tipo que NO es Office (texto plano, no seguro para inline) no
    intenta convertir nada -- el preview es la misma URL de descarga normal
    (que en este caso SÍ fuerza `attachment`, mismo criterio que
    `_download_disposition`)."""
    _, token = _register_login(client)
    file_obj = _upload_with_mime(client, token, b"contenido de texto plano", "pytest_texto.txt", "text/plain")

    resp = client.get(f"/files/{file_obj['id']}/preview", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mime_type"] == file_obj["mime_type"]
    assert body["preview_url"]


# ==================== Éxito + caché -- conversor mockeado ====================

def test_office_preview_converts_once_and_serves_cache_on_second_call(client, db_session, monkeypatch):
    """Primera llamada: no hay cache -> convierte (mock) y sube el PDF a
    MinIO real. Segunda llamada, MISMA versión del archivo: sirve el cache
    sin volver a invocar el conversor."""
    creds, token = _register_login(client)
    file_obj = _upload_with_mime(client, token, b"contenido de un docx de prueba", "pytest_doc.docx", DOCX_MIME)

    calls = []

    def fake_convert(content: bytes, filename: str) -> bytes:
        calls.append(filename)
        return b"%PDF-1.4\n%fake-converted-pdf-from-mock\n"

    monkeypatch.setattr("app.files.router.convert_office_to_pdf", fake_convert)

    from app.files.router import get_file_preview

    user = _get_user(db_session, creds["email"])
    file_row = _get_file_row(db_session, file_obj["id"])

    result_1 = get_file_preview(file_id=file_row.id, db=db_session, current_user=user)
    assert len(calls) == 1
    assert result_1.mime_type == "application/pdf"
    assert result_1.preview_url

    result_2 = get_file_preview(file_id=file_row.id, db=db_session, current_user=user)
    assert len(calls) == 1, "la segunda llamada debe servir el cache, sin reconvertir"
    assert result_2.mime_type == "application/pdf"
    assert result_2.preview_url


def test_office_preview_converter_error_is_translated_to_clear_502(client, db_session, monkeypatch):
    """Si `convert_office_to_pdf` falla (documento corrupto, timeout, lo
    que sea que dispare `RuntimeError` -- ver su docstring en service.py),
    el endpoint traduce eso a un 502 con detalle claro, nunca deja escapar
    la excepción cruda ni un 500 sin contexto."""
    from fastapi import HTTPException

    creds, token = _register_login(client)
    file_obj = _upload_with_mime(client, token, b"otro docx de prueba", "pytest_doc2.docx", DOCX_MIME)

    def fake_convert_fails(content: bytes, filename: str) -> bytes:
        raise RuntimeError("No se pudo generar la vista previa")

    monkeypatch.setattr("app.files.router.convert_office_to_pdf", fake_convert_fails)

    from app.files.router import get_file_preview

    user = _get_user(db_session, creds["email"])
    file_row = _get_file_row(db_session, file_obj["id"])

    with pytest.raises(HTTPException) as exc_info:
        get_file_preview(file_id=file_row.id, db=db_session, current_user=user)

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "No se pudo generar la vista previa"


def test_new_version_invalidates_office_preview_cache(client, db_session, monkeypatch):
    """Subir una versión nueva del archivo (Ronda 4) cambia el
    `version_number` actual -- la key de cache (`file_id` + `version_number`)
    deja de coincidir con la cacheada antes, así que la preview de la
    versión nueva dispara una conversión NUEVA, sin reusar el PDF de la
    versión vieja."""
    creds, token = _register_login(client)
    file_obj = _upload_with_mime(client, token, b"contenido version 1", "pytest_v1.docx", DOCX_MIME)

    calls = []

    def fake_convert(content: bytes, filename: str) -> bytes:
        calls.append(content)
        return b"%PDF-1.4\n%version-" + str(len(calls)).encode() + b"\n"

    monkeypatch.setattr("app.files.router.convert_office_to_pdf", fake_convert)

    from app.files.router import get_file_preview

    user = _get_user(db_session, creds["email"])
    file_row_v1 = _get_file_row(db_session, file_obj["id"])

    get_file_preview(file_id=file_row_v1.id, db=db_session, current_user=user)
    get_file_preview(file_id=file_row_v1.id, db=db_session, current_user=user)
    assert len(calls) == 1  # cache de la v1 funcionando

    # Subir version 2 -- HTTP real contra el servidor vivo (otro proceso),
    # por eso hace falta refrescar la sesión de este test antes de releer.
    version_resp = client.post(
        f"/files/{file_obj['id']}/versions",
        headers=auth_headers(token),
        files={"file": ("pytest_v2.docx", io.BytesIO(b"contenido version 2"), DOCX_MIME)},
    )
    assert version_resp.status_code == 201, version_resp.text

    db_session.expire_all()
    file_row_v2 = _get_file_row(db_session, file_obj["id"])

    get_file_preview(file_id=file_row_v2.id, db=db_session, current_user=user)
    assert len(calls) == 2, "la version nueva debe reconvertir, no reusar el cache de la v1"

    get_file_preview(file_id=file_row_v2.id, db=db_session, current_user=user)
    assert len(calls) == 2, "la segunda llamada sobre la v2 debe cachear igual que la v1"


# ==================== Hallazgo MEDIO de la revisión adversarial (Ronda 5) ====================
# Un archivo Office más grande que el límite del conversor (50MB) viajaba
# completo por la red interna en CADA pedido de preview, siempre fallaba, y
# como nunca se cacheaba el costo se repetía -- confirmado en vivo por el
# equipo de revisión midiendo `rx_bytes` del contenedor `office_converter`.
# Además el endpoint no tenía ningún throttle propio, permitiendo que un
# usuario autenticado normal (rol USER ya tiene `files.download`) monopolice
# la única instancia compartida de `office_converter` a pedidos repetidos.

def test_office_preview_rejects_oversized_file_without_calling_converter(client, db_session, monkeypatch):
    """El backend debe rechazar fail-fast (413) ANTES de leer el objeto de
    MinIO y ANTES de llamar al conversor -- confirmado con un spy sobre
    `convert_office_to_pdf` que nunca debe ejecutarse para este caso."""
    from fastapi import HTTPException

    from app.files.router import MAX_OFFICE_PREVIEW_SOURCE_BYTES, get_file_preview

    creds, token = _register_login(client)

    # +1MB de margen sobre el límite -- no hace falta acercarse más para
    # probar el fail-fast, y mantiene el payload de la prueba lo más chico
    # posible dentro de lo que sigue siendo "más grande que el límite".
    oversized_content = b"\x00" * (MAX_OFFICE_PREVIEW_SOURCE_BYTES + 1024 * 1024)
    file_obj = _upload_with_mime(client, token, oversized_content, "pytest_grande.docx", DOCX_MIME)
    assert file_obj["size_bytes"] > MAX_OFFICE_PREVIEW_SOURCE_BYTES

    calls = []

    def spy_convert(content: bytes, filename: str) -> bytes:
        calls.append(filename)
        return b"%PDF-1.4\nno deberia llegar aca\n"

    monkeypatch.setattr("app.files.router.convert_office_to_pdf", spy_convert)

    user = _get_user(db_session, creds["email"])
    file_row = _get_file_row(db_session, file_obj["id"])

    with pytest.raises(HTTPException) as exc_info:
        get_file_preview(file_id=file_row.id, db=db_session, current_user=user)

    assert exc_info.value.status_code == 413
    assert "tamaño máximo" in exc_info.value.detail
    assert calls == [], "convert_office_to_pdf NUNCA debe llamarse para un archivo que excede el limite"


def test_office_preview_rate_limits_repeated_conversions_per_user(client, db_session, monkeypatch):
    """`OFFICE_PREVIEW_RATE_LIMIT_MAX_CONVERSIONS` conversiones por usuario
    dentro de la ventana se permiten; la siguiente debe dar 429 -- un
    archivo NUEVO por iteración (distinto `file_id`) para que cada llamada
    dispare una conversión real (cache miss) y cuente contra el cupo, en vez
    de servir cache y no consumir nada."""
    from fastapi import HTTPException

    from app.files.router import OFFICE_PREVIEW_RATE_LIMIT_MAX_CONVERSIONS, get_file_preview

    creds, token = _register_login(client)
    user = _get_user(db_session, creds["email"])

    def fake_convert(content: bytes, filename: str) -> bytes:
        return b"%PDF-1.4\n%rate-limit-test\n"

    monkeypatch.setattr("app.files.router.convert_office_to_pdf", fake_convert)

    allowed = 0
    blocked = 0
    total_attempts = OFFICE_PREVIEW_RATE_LIMIT_MAX_CONVERSIONS + 3
    for i in range(total_attempts):
        file_obj = _upload_with_mime(
            client, token, f"contenido distinto {i}".encode(), f"pytest_rl_{i}.docx", DOCX_MIME
        )
        file_row = _get_file_row(db_session, file_obj["id"])
        try:
            get_file_preview(file_id=file_row.id, db=db_session, current_user=user)
            allowed += 1
        except HTTPException as e:
            assert e.status_code == 429, e.detail
            blocked += 1

    assert allowed == OFFICE_PREVIEW_RATE_LIMIT_MAX_CONVERSIONS
    assert blocked == total_attempts - OFFICE_PREVIEW_RATE_LIMIT_MAX_CONVERSIONS
