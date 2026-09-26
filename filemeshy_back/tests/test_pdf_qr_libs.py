"""Ronda 12 (E3) -- red de seguridad para el bump de Pillow 11 -> 12 y pypdf
4 -> 6.

Datos REALES, sin mocks de las librerias: PDF minimo con texto conocido
(escrito byte a byte), PDF truncado, PDF cifrado (pypdf.PdfWriter.encrypt),
PDF "escaneado" (solo imagen, generado con Pillow) que obliga a `_ocr_pdf`, y
el QR de 2FA. Se corren ANTES y DESPUES del bump para comparar.

Cada caso lleva un tope de tiempo (SIGALRM) para que un cuelgue del parser
falle el test en vez de colgar la suite."""
from __future__ import annotations

import base64
import contextlib
import io
import signal
from uuid import UUID


from conftest import auth_headers, login_user, register_user

KEYWORD = "GIRASOL"


@contextlib.contextmanager
def time_limit(seconds: int):
    def _handler(signum, frame):
        raise TimeoutError(f"Superado el tope de {seconds}s")

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def make_text_pdf(text: str) -> bytes:
    """PDF de 1 pagina con texto embebido (Helvetica), armado a mano con
    tabla xref correcta."""
    stream = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def make_scanned_pdf(text: str) -> bytes:
    """PDF cuya unica pagina es una imagen rasterizada (sin capa de texto),
    generado con el plugin PDF de Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1200, 400), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 120), text, fill="black", font=ImageFont.load_default(size=110))
    buf = io.BytesIO()
    image.save(buf, format="PDF", resolution=150.0)
    return buf.getvalue()


def make_encrypted_pdf(text: str) -> bytes:
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(make_text_pdf(text)))
    writer = pypdf.PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.encrypt(user_password="secreta", owner_password="duena", algorithm="AES-256")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _login(client):
    creds = register_user(client)
    return login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]


def _upload_pdf(client, token, content: bytes, name: str = "pytest_doc.pdf") -> dict:
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": (name, io.BytesIO(content), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _wait_worker_done(db_session, file_id: str, timeout: float = 40.0) -> None:
    """El upload encola la indexación y el worker real la procesa EN PARALELO a
    estos tests (que además llaman a `index_file_content` directo). Para no
    correr las dos a la vez sobre el mismo archivo, se espera a que el worker
    termine (estado != 'pending') y recién ahí se re-ejecuta en proceso, de
    forma determinista. Si el worker no responde en `timeout`, se sigue igual
    (la ejecución directa pisa el resultado; el estado final es el mismo)."""
    import time

    from sqlalchemy import text

    deadline = time.time() + timeout
    while time.time() < deadline:
        db_session.expire_all()
        row = db_session.execute(
            text("SELECT extraction_status FROM file_content_index WHERE file_id = :f"), {"f": file_id}
        ).first()
        if row and row[0] != "pending":
            time.sleep(0.3)  # margen: que el worker termine de commitear
            return
        time.sleep(0.3)


def _index(file_id: str, seconds: int = 100, db_session=None):
    from app.worker.tasks.indexing import index_file_content

    if db_session is not None:
        _wait_worker_done(db_session, file_id)
    with time_limit(seconds):
        index_file_content(None, file_id)


def _record(db_session, file_id: str):
    from app.files.repository import file_content_index_repo

    db_session.expire_all()
    return file_content_index_repo.get_by_file_id(db_session, UUID(file_id))


# (i) PDF real con texto embebido ------------------------------------------

def test_extract_pdf_text_reads_embedded_text():
    from app.worker.tasks.indexing import _extract_pdf_text

    with time_limit(30):
        text = _extract_pdf_text(make_text_pdf(f"Documento {KEYWORD} de prueba"))
    assert KEYWORD in text


def test_pdf_text_indexed_end_to_end(client, db_session):
    token = _login(client)
    uploaded = _upload_pdf(client, token, make_text_pdf(f"Informe {KEYWORD} anual"))
    _index(uploaded["id"], 100, db_session)
    rec = _record(db_session, uploaded["id"])
    assert rec.extraction_status == "done", rec.error_message
    assert KEYWORD in rec.content_text


# (ii) PDF corrupto y cifrado -> failed con mensaje, sin colgar --------------

def test_truncated_pdf_ends_failed_with_message(client, db_session):
    token = _login(client)
    good = make_text_pdf(f"Truncado {KEYWORD}")
    uploaded = _upload_pdf(client, token, good[: len(good) // 2], "pytest_trunc.pdf")
    _index(uploaded["id"], 60, db_session)
    rec = _record(db_session, uploaded["id"])
    assert rec.extraction_status == "failed", (rec.extraction_status, rec.error_message)
    assert rec.error_message


def test_garbage_pdf_ends_failed_with_message(client, db_session):
    token = _login(client)
    uploaded = _upload_pdf(client, token, b"%PDF-1.7\n" + b"\x00\xff basura sin estructura " * 50, "pytest_basura.pdf")
    _index(uploaded["id"], 60, db_session)
    rec = _record(db_session, uploaded["id"])
    assert rec.extraction_status == "failed", (rec.extraction_status, rec.error_message)
    assert rec.error_message


def test_encrypted_pdf_ends_failed_with_message(client, db_session):
    token = _login(client)
    uploaded = _upload_pdf(client, token, make_encrypted_pdf(f"Cifrado {KEYWORD}"), "pytest_cifrado.pdf")
    _index(uploaded["id"], 60, db_session)
    rec = _record(db_session, uploaded["id"])
    assert rec.extraction_status == "failed", (rec.extraction_status, rec.error_message)
    assert rec.error_message
    assert rec.content_text is None


# (iii) PDF escaneado -> _ocr_pdf ---------------------------------------------

def test_scanned_pdf_falls_back_to_ocr():
    from app.worker.tasks.indexing import _extract_pdf_text, _extract_text_for_mime

    content = make_scanned_pdf(KEYWORD)
    with time_limit(60):
        assert _extract_pdf_text(content).strip() == ""  # sin capa de texto
        text, status = _extract_text_for_mime(content, "application/pdf")
    assert status == "done"
    assert KEYWORD in text.upper(), f"OCR no leyo la palabra: {text!r}"


# (iv) QR de 2FA -------------------------------------------------------------

def test_totp_qr_is_valid_png():
    from PIL import Image

    from app.auth.service import TOTPService

    b64 = TOTPService.generate_qr_base64("otpauth://totp/FileMeshy:a@example.com?secret=JBSWY3DPEHPK3PXP&issuer=FileMeshy")
    raw = base64.b64decode(b64)
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    image = Image.open(io.BytesIO(raw))
    image.load()
    assert image.format == "PNG" and image.size[0] >= 100 and image.size[0] == image.size[1]
    # Un QR tiene modulos negros y blancos (no una imagen vacia).
    assert image.convert("L").getextrema() == (0, 255)


def test_2fa_setup_endpoint_returns_valid_qr(client):
    from PIL import Image

    token = _login(client)
    resp = client.post("/auth/2fa/setup", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    qr = resp.json()["data"]["qr_code"]
    assert qr.startswith("data:image/png;base64,")
    raw = base64.b64decode(qr.split(",", 1)[1])
    assert raw.startswith(b"\x89PNG")
    Image.open(io.BytesIO(raw)).load()
