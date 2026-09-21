"""Ronda 5 -- preview extendido, Parte 1: video y audio nativo.

Mismo criterio de seguridad que ya se aplica a imágenes/PDF (ver
`app/files/router.py::_resolve_verified_content_type`): el Content-Type
persistido y usado para decidir si se sirve inline SIEMPRE se verifica por
magic bytes, nunca por lo que declaró el cliente al subir. Estos tests
confirman:

1. Un archivo cuyo contenido real es video/audio reconocido termina con el
   mime_type verificado (aunque el cliente declare otra cosa), y su URL de
   descarga NO fuerza `attachment` (se sirve inline, igual que imágenes/PDF).
2. Un archivo que DECLARA ser uno de estos tipos "seguros" pero cuyo
   contenido real no lo confirma se degrada a `application/octet-stream` y
   SÍ fuerza `attachment` -- mismo vector que el hallazgo crítico de Hito 2
   (script disfrazado de imagen), ahora también cubierto para video/audio.
3. El contenedor Ogg (ambiguo entre video/audio) resuelve el mime type final
   según lo que el cliente declaró.

La descarga real no expone la respuesta HTTP con el header
Content-Disposition directo (el endpoint devuelve una URL PRESIGNADA de
MinIO) -- se verifica indirectamente: `generate_presigned_url` solo agrega
el parámetro `response-content-disposition` a la URL cuando
`_download_disposition` decide forzar `attachment` (ver su código), así que
su AUSENCIA en la URL firmada es la señal de que se sirve inline.
"""
import io
from urllib.parse import unquote

from conftest import auth_headers, login_user, register_user


def _register_login(client):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    return creds, token


def _upload(client, token, content: bytes, filename: str, declared_content_type: str):
    resp = client.post(
        "/files/upload",
        headers=auth_headers(token),
        files={"file": (filename, io.BytesIO(content), declared_content_type)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _download_url(client, token, file_id) -> str:
    resp = client.get(f"/files/{file_id}/download", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["download_url"]


def _forces_attachment(download_url: str) -> bool:
    """True si la URL firmada lleva `response-content-disposition=attachment...`
    -- decodificada, porque el valor viaja URL-encoded en el query string."""
    return "attachment" in unquote(download_url).lower()


# ==================== Magic bytes mínimos válidos por formato ====================
# No hace falta contenido real completo -- alcanza con que la firma de bytes
# que `detect_video_type`/`detect_audio_type` buscan esté presente donde
# corresponde (ver app/files/service.py).

def _mp4_bytes() -> bytes:
    # Caja "ftyp" en offset 4 (tamaño de caja de 4 bytes + "ftyp" + brand).
    return b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 8


def _webm_bytes() -> bytes:
    # Magic bytes EBML de Matroska/WebM.
    return b"\x1a\x45\xdf\xa3" + b"\x00" * 16


def _mp3_id3_bytes() -> bytes:
    return b"ID3\x03\x00\x00\x00\x00\x00\x21" + b"\x00" * 16


def _mp3_framesync_bytes() -> bytes:
    return b"\xff\xfb\x90\x00" + b"\x00" * 16


def _wav_bytes() -> bytes:
    # RIFF....WAVE -- tamaño en offset 4 es irrelevante para la detección.
    return b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 8


def _ogg_bytes() -> bytes:
    return b"OggS\x00\x02\x00\x00" + b"\x00" * 16


# ==================== Verificación por contenido real ====================

def test_mp4_content_served_inline_regardless_of_declared_type(client):
    _, token = _register_login(client)
    # Declara un tipo genérico a propósito -- la verificación es por contenido.
    file_obj = _upload(client, token, _mp4_bytes(), "pytest_video.bin", "application/octet-stream")
    assert file_obj["mime_type"] == "video/mp4"

    url = _download_url(client, token, file_obj["id"])
    assert not _forces_attachment(url)


def test_webm_content_verified_and_inline(client):
    _, token = _register_login(client)
    file_obj = _upload(client, token, _webm_bytes(), "pytest_video.webm", "video/webm")
    assert file_obj["mime_type"] == "video/webm"

    url = _download_url(client, token, file_obj["id"])
    assert not _forces_attachment(url)


def test_mp3_id3_header_verified_and_inline(client):
    _, token = _register_login(client)
    file_obj = _upload(client, token, _mp3_id3_bytes(), "pytest_audio.mp3", "audio/mpeg")
    assert file_obj["mime_type"] == "audio/mpeg"

    url = _download_url(client, token, file_obj["id"])
    assert not _forces_attachment(url)


def test_mp3_frame_sync_header_also_detected(client):
    _, token = _register_login(client)
    file_obj = _upload(client, token, _mp3_framesync_bytes(), "pytest_audio2.mp3", "audio/mpeg")
    assert file_obj["mime_type"] == "audio/mpeg"


def test_wav_content_verified_and_inline(client):
    _, token = _register_login(client)
    file_obj = _upload(client, token, _wav_bytes(), "pytest_audio.wav", "audio/wav")
    assert file_obj["mime_type"] == "audio/wav"

    url = _download_url(client, token, file_obj["id"])
    assert not _forces_attachment(url)


def test_ogg_declared_as_video_resolves_to_video_ogg(client):
    _, token = _register_login(client)
    file_obj = _upload(client, token, _ogg_bytes(), "pytest_video.ogv", "video/ogg")
    assert file_obj["mime_type"] == "video/ogg"

    url = _download_url(client, token, file_obj["id"])
    assert not _forces_attachment(url)


def test_ogg_declared_as_audio_resolves_to_audio_ogg(client):
    _, token = _register_login(client)
    file_obj = _upload(client, token, _ogg_bytes(), "pytest_audio.ogg", "audio/ogg")
    assert file_obj["mime_type"] == "audio/ogg"

    url = _download_url(client, token, file_obj["id"])
    assert not _forces_attachment(url)


def test_ogg_with_ambiguous_declared_type_defaults_to_audio_ogg(client):
    """Si el cliente no declaró explícitamente `video/ogg`, el contenedor
    Ogg ambiguo se resuelve como `audio/ogg` (default documentado en
    `_resolve_verified_content_type`)."""
    _, token = _register_login(client)
    file_obj = _upload(client, token, _ogg_bytes(), "pytest_ambiguo.ogg", "application/octet-stream")
    assert file_obj["mime_type"] == "audio/ogg"


# ==================== Contenido falso disfrazado de tipo "seguro" ====================

def test_fake_video_content_declared_as_mp4_is_downgraded_and_forces_download(client):
    """Mismo vector que el hallazgo crítico de Hito 2 (script disfrazado de
    imagen), ahora para video/audio: declarar `video/mp4` no alcanza si el
    contenido real no tiene la caja `ftyp` -- se degrada a un tipo genérico
    y la descarga fuerza `attachment`."""
    _, token = _register_login(client)
    fake_content = b"<script>alert(1)</script>" + b"\x00" * 16
    file_obj = _upload(client, token, fake_content, "pytest_fake.mp4", "video/mp4")

    assert file_obj["mime_type"] == "application/octet-stream"

    url = _download_url(client, token, file_obj["id"])
    assert _forces_attachment(url)


def test_fake_audio_content_declared_as_mp3_is_downgraded(client):
    _, token = _register_login(client)
    fake_content = b"esto no es audio real, es texto plano" + b"\x00" * 8
    file_obj = _upload(client, token, fake_content, "pytest_fake.mp3", "audio/mpeg")

    assert file_obj["mime_type"] == "application/octet-stream"

    url = _download_url(client, token, file_obj["id"])
    assert _forces_attachment(url)


# ==================== Versiones nuevas (Ronda 4 + Ronda 5) ====================

def test_new_version_content_is_also_verified(client):
    """`_create_new_file_version` reusa el mismo `_resolve_verified_content_type`
    que el upload inicial -- confirmarlo con una versión 2 que sube contenido
    de video real sobre un archivo que empezó como texto plano."""
    _, token = _register_login(client)
    file_obj = _upload(client, token, b"contenido de texto original", "pytest_v1.txt", "text/plain")
    assert file_obj["mime_type"] not in ("video/mp4",)

    resp = client.post(
        f"/files/{file_obj['id']}/versions",
        headers=auth_headers(token),
        files={"file": ("pytest_v2.mp4", io.BytesIO(_mp4_bytes()), "video/mp4")},
    )
    assert resp.status_code == 201, resp.text
    updated = resp.json()
    assert updated["mime_type"] == "video/mp4"

    url = _download_url(client, token, file_obj["id"])
    assert not _forces_attachment(url)
