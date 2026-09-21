"""Ronda 6 -- extracción vía OCR (Tesseract) sobre imágenes, y comportamiento
para tipos mime NO soportados (video/audio, legacy Office, binarios --
limitación conocida y documentada de esta ronda, no bloqueante).

El test de OCR sobre imagen depende de que la imagen del stack tenga
`tesseract-ocr`/`tesseract-ocr-spa` instalados (ver Dockerfile) -- solo
corre contra la imagen YA RECONSTRUIDA con el Dockerfile de esta ronda, no
contra el contenedor viejo de Rondas 1-5 (que no tiene Tesseract). Tesseract
no es 100% preciso reconociendo texto renderizado con la fuente default de
Pillow a baja resolución -- el assert es LAXO a propósito: alcanza con que
la palabra clave aparezca en el texto extraído, sin exigir coincidencia
exacta de todo el string.

Cobertura pendiente de OCR que NO entra en esta ronda (documentado, no
bloqueante -- ver PENDIENTES.md): OCR sobre un PDF escaneado real
(`_ocr_pdf`, el fallback de `_extract_pdf_text` cuando el PDF no trae texto
embebido) no se cubre acá con un archivo real -- generar un PDF
"escaneado" de verdad (una página que sea solo una imagen rasterizada, sin
capa de texto) para el test hubiera consumido más tiempo del que esta
ronda tenía disponible. La extracción de texto EMBEBIDO de un PDF normal sí
la ejercitan indirectamente los tests de `test_preview_office.py`/uploads
existentes en cuanto a que el mime type se reconoce, pero ningún test de
esta ronda sube un PDF de verdad y confirma su `content_text` -- limitación
conocida a cerrar en una ronda futura."""
import io
from uuid import UUID

from conftest import auth_headers, login_user, register_user


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
    directo en el proceso de test (sin Celery/broker real) -- mismo patrón
    que `test_content_indexing.py`."""
    from app.worker.tasks.indexing import index_file_content

    index_file_content(None, file_id)


def _make_text_image(text: str) -> bytes:
    """Imagen PNG simple: fondo blanco, texto negro dibujado con la fuente
    default de Pillow (`ImageFont.load_default()`, siempre disponible sin
    depender de que haya fuentes TTF instaladas en el sistema)."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (600, 150), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 50), text, fill="black")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_ocr_extracts_text_from_image(client, db_session):
    """Sube una imagen con texto renderizado, corre la extracción, y
    confirma que Tesseract reconoció (al menos parte de) la palabra clave."""
    from app.files.repository import file_content_index_repo

    keyword = "GIRASOL"
    content = _make_text_image(keyword)
    _, token = _register_login(client)
    uploaded = _upload(client, token, content, "pytest_cartel.png", "image/png")

    _index_now(uploaded["id"])

    record = file_content_index_repo.get_by_file_id(db_session, UUID(uploaded["id"]))
    assert record is not None
    assert record.extraction_status == "done", record.error_message
    assert record.content_text is not None
    assert keyword.upper() in record.content_text.upper(), (
        f"OCR no reconoció la palabra clave -- texto extraído: {record.content_text!r}"
    )


def test_unsupported_mime_type_marks_status_unsupported(client, db_session):
    """Audio (mp3 real por magic bytes -- header ID3) -- tipo mime declarado
    'unsupported' sin intentar ninguna extracción (nunca se intenta
    decodificarlo como texto ni nada parecido). No debe romper la tarea ni
    dejar el worker en un estado raro."""
    from app.files.repository import file_content_index_repo

    _, token = _register_login(client)
    # Header ID3 real (magic bytes que reconoce detect_audio_type) + relleno
    # -- no necesita ser un mp3 válido de verdad, solo pasar la verificación
    # de contenido real que hace _resolve_verified_content_type en el upload.
    fake_mp3 = b"ID3" + b"\x00" * 20
    uploaded = _upload(client, token, fake_mp3, "pytest_audio.mp3", "audio/mpeg")
    assert uploaded["mime_type"] == "audio/mpeg"

    _index_now(uploaded["id"])

    record = file_content_index_repo.get_by_file_id(db_session, UUID(uploaded["id"]))
    assert record is not None
    assert record.extraction_status == "unsupported"
    assert record.content_text is None
