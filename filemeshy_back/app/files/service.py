"""Servicio de archivos: almacenamiento (MinIO), compresión de imágenes y
validación de contenido.

Fusiona, durante la migración a monolito modular:
- app/services/storage_service.py (subida/borrado/URLs de MinIO)
- app/services/image_processing.py (compresión/redimensionado a WebP)
- app/utils/image_validation.py (validación de imágenes por magic bytes)

Módulo aún sin construir de verdad (no tiene router.py/repository.py/
schemas.py/models.py reales todavía) -- ver "Backend/Files - Qué es y cómo se
usa.md" en Obsidian. No se inventa contenido que no existe hoy.

Estructura de paths preparada para multi-tenant:
  filemeshy-media/{company_code}/{modulo}/{id_opcional}/{uuid}.ext

Ej:
  filemeshy-media/acme-corp/folders/folder-42/uuid.jpg
  filemeshy-media/acme-corp/branding/uuid.png
"""

import io
import json
import logging
import socket
import struct
import time
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

_client = None
_init_ok = False  # Solo True si la inicialización fue exitosa
_bucket_ensured: set[str] = set()  # Buckets ya verificados/creados
_presign_client = None
_presign_init_ok = False


def _get_client():
    """Retorna el cliente boto3 configurado para MinIO.
    Reintenta en cada llamada hasta tener éxito (no cachea fallos).
    """
    global _client, _init_ok

    if _init_ok:
        return _client

    from app.core.config import settings

    if not settings.MINIO_ENDPOINT:
        logger.warning("[Storage] MINIO_ENDPOINT no configurado — almacenamiento deshabilitado")
        return None

    try:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "s3",
            endpoint_url=settings.MINIO_ENDPOINT,
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        _init_ok = True
        logger.info(f"[Storage] Cliente MinIO inicializado en {settings.MINIO_ENDPOINT}")
    except Exception as e:
        logger.error(f"[Storage] Error inicializando cliente MinIO: {e}")
        _client = None

    return _client


def _get_presign_client():
    """Cliente boto3 separado del de `_get_client()`, dedicado exclusivamente a
    firmar URLs (`generate_presigned_url`).

    Por qué un cliente aparte: la firma SigV4 de una URL presignada incluye el
    host como canonical header -- si se firma con el endpoint INTERNO
    (`MINIO_ENDPOINT`, ej. http://minio:9000 dentro de Docker) pero el navegador
    la resuelve contra un host distinto, MinIO recalcula la firma con el Host
    real de la request entrante y no coincide (403). Este cliente firma
    directamente contra `MINIO_PUBLIC_URL` (el host que el navegador sí puede
    resolver), igual que `get_public_url()` ya reconstruye URLs públicas para
    el resto del storage.
    """
    global _presign_client, _presign_init_ok

    if _presign_init_ok:
        return _presign_client

    from app.core.config import settings

    endpoint = settings.MINIO_PUBLIC_URL or settings.MINIO_ENDPOINT
    if not endpoint:
        logger.warning("[Storage] MINIO_PUBLIC_URL/MINIO_ENDPOINT no configurado — firma de URLs deshabilitada")
        return None

    try:
        import boto3
        from botocore.config import Config

        _presign_client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        _presign_init_ok = True
        logger.info(f"[Storage] Cliente de firma MinIO inicializado en {endpoint}")
    except Exception as e:
        logger.error(f"[Storage] Error inicializando cliente de firma MinIO: {e}")
        _presign_client = None

    return _presign_client


def _ensure_bucket(bucket: str) -> None:
    """Crea el bucket si no existe y establece política de lectura pública.
    Solo lo hace una vez por proceso (cache en _bucket_ensured).
    """
    global _bucket_ensured

    if bucket in _bucket_ensured:
        return

    client = _get_client()
    if not client:
        return

    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        try:
            client.create_bucket(Bucket=bucket)
            logger.info(f"[Storage] Bucket '{bucket}' creado")
        except Exception as e:
            logger.error(f"[Storage] Error creando bucket '{bucket}': {e}")
            return

    policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},
            "Action": ["s3:GetObject"],
            "Resource": [f"arn:aws:s3:::{bucket}/*"],
        }],
    })
    try:
        client.put_bucket_policy(Bucket=bucket, Policy=policy)
        logger.info(f"[Storage] Política pública aplicada en bucket '{bucket}'")
    except Exception as e:
        logger.warning(f"[Storage] No se pudo aplicar política pública en '{bucket}': {e}")

    _bucket_ensured.add(bucket)


def _ensure_private_bucket(bucket: str) -> None:
    """Crea el bucket si no existe, SIN aplicar ninguna política de lectura pública
    (a diferencia de `_ensure_bucket`). MinIO deniega por defecto cualquier acceso
    a un bucket sin política -- el único acceso de lectura válido es una URL
    firmada de corta duración (ver `generate_presigned_url`).

    Usar exclusivamente para contenido PII (fotos de identificación de clientes).
    """
    global _bucket_ensured

    if bucket in _bucket_ensured:
        return

    client = _get_client()
    if not client:
        return

    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        try:
            client.create_bucket(Bucket=bucket)
            logger.info(f"[Storage] Bucket privado '{bucket}' creado (sin política pública)")
        except Exception as e:
            logger.error(f"[Storage] Error creando bucket privado '{bucket}': {e}")
            return

    _bucket_ensured.add(bucket)


def upload_private_file(
    path: str,
    content: bytes,
    extension: str,
    content_type: str = "application/octet-stream",
) -> str:
    """Sube un archivo al bucket PRIVADO (`settings.MINIO_PRIVATE_BUCKET`), sin
    política de lectura pública. Usar para PII (documentos de identidad).

    Args:
        path: Prefijo/ruta dentro del bucket, sin slash final.
        content: Bytes del archivo.
        extension: Extensión con punto, ej: ".webp" o ".pdf"
        content_type: MIME type del archivo.

    Returns:
        Key relativa del archivo en el bucket privado. Para leerlo, generar
        una URL firmada con `generate_presigned_url()` -- NUNCA `get_public_url()`.

    Raises:
        RuntimeError si MinIO no está disponible o la subida falla.
    """
    from app.core.config import settings

    client = _get_client()
    if not client:
        raise RuntimeError("El servicio de almacenamiento (MinIO) no está configurado")

    bucket = settings.MINIO_PRIVATE_BUCKET
    _ensure_private_bucket(bucket)

    # UUID v7 (norma del proyecto: todo ID nuevo es v7, nunca v4) -- mismo
    # helper que usan los modelos para sus PKs, ver app/shared/utils/uuid7.py.
    from app.shared.utils.uuid7 import uuid7
    key = f"{path.strip('/')}/{uuid7()}{extension}"

    try:
        client.upload_fileobj(
            io.BytesIO(content),
            bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
    except Exception as e:
        logger.error(f"[Storage] Error subiendo archivo privado a {bucket}/{key}: {e}")
        raise RuntimeError(f"Error al subir archivo: {e}")

    logger.info(f"[Storage] Subido (privado): {bucket}/{key}")
    return key


def delete_private_file(key: str) -> None:
    """Elimina un archivo del bucket privado a partir de su key relativa.
    No lanza excepción si el archivo no existe o MinIO no está disponible.
    """
    from app.core.config import settings

    client = _get_client()
    if not client:
        return

    bucket = settings.MINIO_PRIVATE_BUCKET
    try:
        client.delete_object(Bucket=bucket, Key=key.lstrip("/"))
        logger.info(f"[Storage] Eliminado (privado): {bucket}/{key}")
    except Exception as e:
        logger.warning(f"[Storage] Error eliminando archivo privado '{key}': {e}")


def generate_presigned_url(
    key: str,
    expires_seconds: int = 600,
    response_content_disposition: Optional[str] = None,
) -> str:
    """Genera una URL firmada de corta duración para leer un archivo del bucket
    PRIVADO. La URL expira sola -- no requiere revocación.

    Args:
        key: Key relativa del archivo (tal como la devolvió `upload_private_file`).
        expires_seconds: Vigencia de la URL en segundos (default 600 = 10 min).
        response_content_disposition: Si se pasa (ej. 'attachment; filename="x.pdf"'),
            fuerza esa cabecera en la respuesta de MinIO/S3 -- usado para forzar
            descarga de PDFs en vez de que el navegador los renderice inline
            (un PDF puede traer JS embebido).

    Raises:
        RuntimeError si MinIO no está disponible o la firma falla.
    """
    from app.core.config import settings

    client = _get_presign_client()
    if not client:
        raise RuntimeError("El servicio de almacenamiento (MinIO) no está configurado")

    bucket = settings.MINIO_PRIVATE_BUCKET
    params = {"Bucket": bucket, "Key": key.lstrip("/")}
    if response_content_disposition:
        params["ResponseContentDisposition"] = response_content_disposition

    try:
        return client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires_seconds,
        )
    except Exception as e:
        logger.error(f"[Storage] Error generando URL firmada para {bucket}/{key}: {e}")
        raise RuntimeError(f"Error al generar URL firmada: {e}")


def upload_file(
    path: str,
    content: bytes,
    extension: str,
    content_type: str = "application/octet-stream",
) -> str:
    """Sube un archivo al bucket único de la aplicación.

    Args:
        path: Prefijo/ruta dentro del bucket, sin slash final.
              Ej: "acme-corp/folders/folder-42"
        content: Bytes del archivo.
        extension: Extensión con punto, ej: ".jpg"
        content_type: MIME type del archivo.

    Returns:
        Key relativa del archivo en el bucket, sin hostname ni puerto.
        Ej: "acme-corp/folders/folder-42/{uuid}.jpg"
        Usar get_public_url() para obtener la URL pública completa.

    Raises:
        RuntimeError si MinIO no está disponible o la subida falla.
    """
    from app.core.config import settings

    client = _get_client()
    if not client:
        raise RuntimeError("El servicio de almacenamiento (MinIO) no está configurado")

    bucket = settings.MINIO_BUCKET
    _ensure_bucket(bucket)

    key = f"{path.strip('/')}/{uuid.uuid4()}{extension}"

    try:
        client.upload_fileobj(
            io.BytesIO(content),
            bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
    except Exception as e:
        logger.error(f"[Storage] Error subiendo archivo a {bucket}/{key}: {e}")
        raise RuntimeError(f"Error al subir archivo: {e}")

    logger.info(f"[Storage] Subido: {bucket}/{key}")
    return key


def delete_file(path: str) -> None:
    """Elimina un archivo a partir de su key relativa o URL completa.
    Acepta ambos formatos para compatibilidad con datos existentes en BD.
    No lanza excepción si el archivo no existe o MinIO no está disponible.
    """
    from app.core.config import settings

    client = _get_client()
    if not client:
        return

    bucket = settings.MINIO_BUCKET
    try:
        if path.startswith("http"):
            # URL completa (datos existentes): extraer key
            parts = path.split(f"/{bucket}/", 1)
            if len(parts) != 2:
                logger.warning(f"[Storage] No se pudo extraer key de URL: {path}")
                return
            key = parts[1]
        else:
            # Key relativa (datos nuevos): usar directamente
            key = path.lstrip("/")

        client.delete_object(Bucket=bucket, Key=key)
        logger.info(f"[Storage] Eliminado: {bucket}/{key}")
    except Exception as e:
        logger.warning(f"[Storage] Error eliminando '{path}': {e}")


def to_storage_key(url: str) -> str:
    """Convierte una URL completa de MinIO a su key relativa para guardar en BD.
    Si ya es una key relativa o una URL externa (no MinIO), la devuelve sin cambios.
    Usar en validators de schemas de entrada que reciban URLs de MinIO.
    """
    if not url or not url.startswith("http"):
        return url  # ya es key relativa o vacío

    from app.core.config import settings
    bucket = settings.MINIO_BUCKET or "filemeshy-media"
    parts = url.split(f"/{bucket}/", 1)
    if len(parts) == 2:
        return parts[1]  # extraer key
    return url  # URL externa — devolver tal cual


def is_minio_url(path: str) -> bool:
    """Retorna True si el valor es una ruta almacenada en MinIO
    (key relativa o URL absoluta de MinIO), no una URL externa ni ruta local.
    """
    if not path:
        return False
    # Ruta local del filesystem — no es MinIO
    if path.startswith("/"):
        return False
    # URL absoluta — solo es MinIO si apunta a nuestro endpoint
    if path.startswith("http"):
        from app.core.config import settings
        base = settings.MINIO_PUBLIC_URL or settings.MINIO_ENDPOINT
        if not base:
            return False
        return path.startswith(base.rstrip("/"))
    # Key relativa sin esquema — pertenece a nuestro storage
    return True


def get_public_url(stored_path: Optional[str]) -> Optional[str]:
    """Convierte cualquier ruta almacenada en BD a una URL pública válida usando
    el MINIO_PUBLIC_URL *actual* de la configuración.

    Casos que maneja:
    - URL absoluta MinIO con cualquier hostname (http://minio:9000/...,
      http://localhost:9000/..., http://localhost:9300/...)  →  reconstruida
      con MINIO_PUBLIC_URL actual, sin importar con qué hostname fue guardada.
    - Ruta local del filesystem (/static/uploads/...)  →  devuelta tal cual;
      el frontend la prefija con el API base URL.
    - Clave relativa de MinIO (company/logos/uuid.jpg)  →  URL completa.
    - None / string vacío  →  None.

    Esto garantiza que cambiar MINIO_PUBLIC_URL o MINIO_ENDPOINT nunca deja
    URLs rotas en la BD: siempre se usa el valor configurado en ese momento.
    """
    if not stored_path:
        return stored_path

    from app.core.config import settings
    from urllib.parse import urlparse

    # Ruta local del filesystem — el frontend añade el base URL del API
    if stored_path.startswith("/"):
        return stored_path

    # URL absoluta (MinIO con cualquier hostname)
    # Extraer solo el path (/bucket/key) y reconstruir con MINIO_PUBLIC_URL actual
    if stored_path.startswith("http"):
        parsed = urlparse(stored_path)
        path_part = parsed.path  # ej: /filemeshy-media/company/logos/uuid.jpg
        public_base = (settings.MINIO_PUBLIC_URL or settings.MINIO_ENDPOINT or "").rstrip("/")
        if not public_base:
            return stored_path
        return f"{public_base}{path_part}"

    # Clave relativa sin esquema (company/logos/uuid.jpg)
    bucket = settings.MINIO_BUCKET or "filemeshy-media"
    public_base = (settings.MINIO_PUBLIC_URL or settings.MINIO_ENDPOINT or "").rstrip("/")
    if not public_base:
        return stored_path
    return f"{public_base}/{bucket}/{stored_path}"


# ---------------------------------------------------------------------------
# Compresión de imágenes (antes app/services/image_processing.py)
# ---------------------------------------------------------------------------
# Decidido usar pyvips (bindings de libvips) in-process en vez de un servicio
# aparte tipo imgproxy — no agrega nada nuevo al stack. Ver PENDIENTES.md item G12.

MAX_DIMENSION = 1600
WEBP_QUALITY = 80


def compress_image(content: bytes, fmt: str, quality: int = WEBP_QUALITY) -> tuple[bytes, str]:
    """Redimensiona (tope 1600px de lado mayor) y reencoda a WebP.

    SVG se devuelve sin cambios — es vectorial, comprimirlo no aplica. Un GIF animado
    también se devuelve sin cambios: pyvips solo cargaría el primer frame, y perder la
    animación es peor que el peso actual. Cualquier error de pyvips degrada al
    contenido original en vez de romper la subida.

    Args:
        content: Bytes originales del archivo.
        fmt: Formato detectado por `validate_image_content`/`detect_image_type`
             (ej. 'jpeg', 'png', 'gif', 'webp', 'svg').
        quality: Calidad WebP (0-100). Default 80 (WEBP_QUALITY) para no romper
                 a los llamadores existentes. Usar un valor mayor (ej. 90) para
                 contenido donde la legibilidad importa más que el peso, como
                 fotos de documento de identidad.

    Returns:
        (contenido_final, extension_final) — extension_final es ".webp" si se
        comprimió, o la extensión original (con punto) si se dejó tal cual.
    """
    orig_ext = ".jpg" if fmt == "jpeg" else f".{fmt}"

    if fmt == "svg":
        return content, orig_ext

    try:
        import pyvips
    except ImportError:
        logger.warning("[ImageProcessing] pyvips no disponible — subiendo imagen sin comprimir")
        return content, orig_ext

    try:
        image = pyvips.Image.new_from_buffer(content, "", access="sequential")

        if fmt == "gif" and image.get_n_pages() > 1:
            return content, orig_ext

        if image.width > MAX_DIMENSION or image.height > MAX_DIMENSION:
            scale = MAX_DIMENSION / max(image.width, image.height)
            image = image.resize(scale)

        webp_bytes = image.write_to_buffer(".webp", Q=quality)
        return webp_bytes, ".webp"
    except Exception as e:
        logger.warning(f"[ImageProcessing] Error comprimiendo imagen, se sube sin cambios: {e}")
        return content, orig_ext


# ---------------------------------------------------------------------------
# Validación de imágenes por magic bytes (antes app/utils/image_validation.py)
# ---------------------------------------------------------------------------
# Verifica que el contenido binario del archivo sea realmente una imagen,
# independientemente del nombre o extensión del archivo. Sin dependencias externas.

# Firmas de bytes conocidas para cada formato
_SIGNATURES: list[tuple[bytes, str]] = [
    (b'\xff\xd8\xff',          'jpeg'),
    (b'\x89PNG\r\n\x1a\n',     'png'),
    (b'GIF87a',                 'gif'),
    (b'GIF89a',                 'gif'),
    (b'RIFF',                   'webp'),   # también verifica "WEBP" en offset 8
    (b'<svg',                   'svg'),
    (b'<?xml',                  'svg'),    # SVG puede comenzar con declaración XML
]

_MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def detect_image_type(content: bytes) -> str | None:
    """Detecta el tipo de imagen por magic bytes.

    Returns:
        Nombre del formato ('jpeg', 'png', 'gif', 'webp', 'svg')
        o None si no se reconoce como imagen válida.
    """
    if not content:
        return None

    header = content[:12]

    for signature, fmt in _SIGNATURES:
        if header.startswith(signature):
            # WebP necesita verificación adicional: bytes 8-11 deben ser "WEBP"
            if fmt == 'webp' and header[8:12] != b'WEBP':
                continue
            # SVG: verificar que realmente contenga la etiqueta <svg en el texto
            if fmt == 'svg':
                try:
                    sample = content[:1024].decode('utf-8', errors='ignore').lower()
                    if '<svg' not in sample:
                        continue
                except Exception:
                    continue
            return fmt

    return None


def validate_image_content(
    content: bytes,
    allowed_formats: set[str] | None = None,
    max_size: int = _MAX_IMAGE_SIZE_BYTES,
) -> str:
    """Valida que el contenido sea una imagen real y retorna el formato detectado.

    Args:
        content: Bytes del archivo subido.
        allowed_formats: Formatos permitidos, ej: {'jpeg', 'png', 'svg'}.
                         Si es None, acepta todos los formatos reconocidos.
        max_size: Tamaño máximo en bytes (default 10 MB).

    Returns:
        Nombre del formato detectado.

    Raises:
        ValueError con mensaje descriptivo si la validación falla.
    """
    if len(content) > max_size:
        mb = max_size // (1024 * 1024)
        raise ValueError(f"El archivo supera el tamaño máximo permitido ({mb} MB)")

    if len(content) < 8:
        raise ValueError("El archivo está vacío o es demasiado pequeño")

    fmt = detect_image_type(content)

    if fmt is None:
        raise ValueError(
            "El archivo no es una imagen válida. "
            "Solo se permiten PNG, JPG, GIF, WebP y SVG."
        )

    if allowed_formats and fmt not in allowed_formats:
        readable = ", ".join(sorted(allowed_formats)).upper()
        raise ValueError(f"Formato '{fmt.upper()}' no permitido. Use: {readable}")

    return fmt


def is_pdf_content(content: bytes) -> bool:
    """Valida por magic bytes que el contenido sea realmente un PDF.

    El header estándar es "%PDF-" al inicio del archivo, pero algunos PDF
    generados con basura previa (BOM, whitespace) lo corren unos bytes -- el
    spec de PDF tolera esto y los lectores reales (ej. Adobe) buscan "%PDF-"
    en los primeros 1024 bytes en vez de exigirlo en offset 0.
    """
    if not content:
        return False
    return b"%PDF-" in content[:1024]


# ---------------------------------------------------------------------------
# Validación de video/audio por magic bytes (Ronda 5: preview extendido)
# ---------------------------------------------------------------------------
# Mismo criterio que la validación de imágenes de arriba: nunca confiar en el
# nombre/Content-Type declarado por el cliente para decidir si un archivo se
# sirve inline -- se verifica el contenido real.
#
# El contenedor Ogg (magic bytes "OggS") es compartido por video/ogg y
# audio/ogg -- distinguirlos de verdad requeriría parsear los streams
# internos del contenedor (qué códec llevan los packets), fuera de alcance
# acá. `detect_video_type`/`detect_audio_type` devuelven ambos 'ogg' en ese
# caso -- el caller (ver `_resolve_verified_content_type` en el router)
# decide cuál de los dos mime types final usar según lo que el propio
# usuario declaró al subir.

def detect_video_type(content: bytes) -> str | None:
    """Detecta contenedor de video por magic bytes.

    Returns:
        'mp4' (caja "ftyp" en offset 4), 'webm' (magic bytes EBML
        1A 45 DF A3), 'ogg' (magic bytes "OggS", ambiguo con audio/ogg,
        ver docstring del módulo), o None si no se reconoce.
    """
    if not content or len(content) < 12:
        return None
    if content[4:8] == b'ftyp':
        return 'mp4'
    if content[:4] == b'\x1a\x45\xdf\xa3':
        return 'webm'
    if content[:4] == b'OggS':
        return 'ogg'
    return None


def detect_audio_type(content: bytes) -> str | None:
    """Detecta formato/contenedor de audio por magic bytes.

    Returns:
        'mpeg' (mp3 -- header ID3 o frame sync FF FB/FF F3/FF F2), 'wav'
        (RIFF + "WAVE" en offset 8), 'ogg' (magic bytes "OggS", ambiguo con
        video/ogg, ver docstring del módulo), o None si no se reconoce.
    """
    if not content or len(content) < 12:
        return None
    if content[:3] == b'ID3':
        return 'mpeg'
    if content[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'):
        return 'mpeg'
    if content[:4] == b'RIFF' and content[8:12] == b'WAVE':
        return 'wav'
    if content[:4] == b'OggS':
        return 'ogg'
    return None


# ---------------------------------------------------------------------------
# Conversión de documentos Office a PDF (Ronda 5: preview extendido)
# ---------------------------------------------------------------------------
# El backend NUNCA convierte Office a PDF en proceso -- delega a un servicio
# Docker aislado (`filemeshy_office_converter/`, construido en paralelo por
# otro agente de esta misma ronda) vía HTTP interno. Aislar la conversión en
# su propio contenedor evita correr LibreOffice (o lo que sea que use ese
# servicio) con los mismos privilegios que el backend -- un documento Office
# malicioso que explote el conversor queda contenido ahí, no en el proceso
# que tiene las credenciales de MinIO/Postgres.
#
# Contrato asumido con ese servicio (ver `settings.OFFICE_CONVERTER_URL`):
#   POST {OFFICE_CONVERTER_URL}/convert   (multipart, campo "file")
#   200  -> body = bytes del PDF convertido (Content-Type: application/pdf)
#   4xx/5xx -> body = JSON {"detail": "..."} con el motivo del rechazo
#              (documento corrupto, formato no soportado, timeout interno)
# Si el contrato real termina siendo distinto, ajustar SOLO esta función.

OFFICE_CONVERTER_TIMEOUT_SECONDS = 35  # el conversor timeoutea a ~30s, más margen


def convert_office_to_pdf(content: bytes, filename: str) -> bytes:
    """Convierte un documento Office a PDF llamando al servicio aislado
    `office_converter`. Nunca deja pasar una excepción cruda de red/timeout
    al caller -- siempre `RuntimeError` con un mensaje apto para mostrar tal
    cual al usuario final (ver Ronda 5, contrato pedido: "No se pudo generar
    la vista previa", nunca un 500 crudo).
    """
    import httpx

    from app.core.config import settings

    url = f"{settings.OFFICE_CONVERTER_URL.rstrip('/')}/convert"

    try:
        response = httpx.post(
            url,
            files={"file": (filename, content)},
            timeout=OFFICE_CONVERTER_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as e:
        logger.error(f"[OfficeConverter] Timeout convirtiendo '{filename}': {e}")
        raise RuntimeError("No se pudo generar la vista previa") from e
    except httpx.HTTPError as e:
        logger.error(f"[OfficeConverter] Error de conexión convirtiendo '{filename}': {e}")
        raise RuntimeError("No se pudo generar la vista previa") from e

    if response.status_code >= 400:
        detail = None
        try:
            detail = response.json().get("detail")
        except Exception:
            pass
        logger.error(
            f"[OfficeConverter] Conversión rechazada para '{filename}' "
            f"({response.status_code}): {detail}"
        )
        raise RuntimeError("No se pudo generar la vista previa")

    return response.content


# ---------------------------------------------------------------------------
# Cache de previews (Office -> PDF) en el bucket privado (Ronda 5)
# ---------------------------------------------------------------------------
# A diferencia de `upload_private_file` (key con uuid aleatorio, pensada para
# blobs de archivo), el cache de preview necesita una key DETERMINISTA
# (file_id + version_number) para poder chequear "¿ya existe?" antes de
# volver a convertir.

def office_preview_key(file_id, version_number: int) -> str:
    """Key determinista del PDF cacheado de la preview de `file_id` en su
    `version_number` ACTUAL -- si se sube una versión nueva o se restaura
    una vieja (Ronda 4, `File.storage_key` cambia pero el número de versión
    avanza igual, ver `_create_new_file_version`/`restore_file_version`),
    el número cambia y esta key deja de coincidir con ninguna cacheada
    antes -- el cache de la versión vieja queda huérfano (nunca se sirve por
    error) sin necesidad de invalidarlo a mano."""
    return f"previews/{file_id}/{version_number}.pdf"


def object_exists_private(key: str) -> bool:
    """True si `key` ya existe en el bucket privado (HEAD, sin traer el
    contenido) -- usado para decidir si hace falta convertir de nuevo o si
    ya hay un PDF cacheado servible tal cual."""
    from app.core.config import settings

    client = _get_client()
    if not client:
        return False
    try:
        client.head_object(Bucket=settings.MINIO_PRIVATE_BUCKET, Key=key.lstrip("/"))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Antivirus (Ronda 7): escaneo de malware vía ClamAV antes de subir a MinIO
# ---------------------------------------------------------------------------
# El backend NUNCA sube contenido nuevo a MinIO sin escanearlo primero (ver
# `_scan_for_malware_or_raise` en router.py, enganchado en los dos únicos
# lugares donde entra contenido nuevo al sistema: `_validate_and_store_upload`
# y `_create_new_file_version`). `clamd` corre en su propio contenedor
# aislado (`clamav/clamav:stable`, ver docker-compose.yml) -- mismo criterio
# de aislamiento que `office_converter` en Ronda 5, aunque acá no hace falta
# construir nada custom: la imagen oficial ya trae `freshclam` para mantener
# las firmas actualizadas.
#
# Protocolo TCP INSTREAM implementado a mano con sockets crudos, sin
# dependencia de terceros -- es simple (chunks con longitud prefijada de 4
# bytes + comando "zINSTREAM\0") y esto es justamente el tipo de componente
# de seguridad donde vale más tener control total del manejo de errores
# (política fail-closed, ver docstring de `scan_for_malware`) que ahorrarse
# unas líneas con una librería cliente de la que no se audita el código.
# Referencia del protocolo: https://docs.clamav.net/manual/Usage/Scanning.html

_CLAMAV_CHUNK_SIZE = 8192  # tamaño de chunk arbitrario, cualquier valor razonable sirve


class _ScanDeadlineExceeded(Exception):
    """Señal interna (nunca se propaga fuera de `scan_for_malware`): se
    agotó el presupuesto TOTAL de `CLAMAV_SCAN_TIMEOUT_SECONDS`, ver
    `scan_for_malware` -- hallazgo de la revisión adversarial (Ronda 7):
    `sock.settimeout()` por sí solo es un timeout de INACTIVIDAD por
    syscall, se resetea en cada `send`/`recv` individual, así que un peer
    que responde a los tumbos (unos bytes cada tanto, cada intervalo por
    debajo del timeout configurado) puede estirar la conexión mucho más
    allá del tiempo "documentado" sin disparar nunca un `socket.timeout`.
    Reproducido en vivo por la revisión: timeout=2s, servidor fake devolviendo
    1 byte cada 1.5s -> el escaneo tardó 15s (7.5x lo configurado)."""


def scan_for_malware(content: bytes) -> tuple[bool, Optional[str]]:
    """Escanea `content` contra `clamd` real (nunca simulado) vía TCP
    INSTREAM, con un deadline TOTAL real (no solo timeout de inactividad
    por syscall, ver `_ScanDeadlineExceeded`): antes de cada `send`/`recv`
    se recalcula el tiempo remanente contra `CLAMAV_SCAN_TIMEOUT_SECONDS` y
    se usa ESE remanente como timeout de la próxima syscall -- así ninguna
    combinación de operaciones lentas puede hacer que la función completa
    tarde más que el timeout configurado (con margen chico de overhead
    real de red, no varios múltiplos).

    Función SÍNCRONA y bloqueante a propósito (sockets crudos, sin
    async) -- el caller (`_scan_for_malware_or_raise` en router.py) la
    corre en threadpool (`run_in_threadpool`), nunca directo en el loop de
    asyncio (hallazgo de la revisión adversarial, Ronda 7: sin eso, un
    escaneo de ~2s con un archivo grande congelaba el backend ENTERO para
    todos los usuarios, no solo para quien subía).

    Returns:
        (es_limpio, nombre_de_amenaza) -- `nombre_de_amenaza` es `None`
        cuando `es_limpio` es `True`.

    Raises:
        ConnectionError si `clamd` no responde, se corta la conexión, se
        agota el deadline total, o devuelve una respuesta que no se puede
        interpretar. A propósito NO se atrapa acá ni se traduce a "está
        limpio" -- el caller es quien decide la política fail-closed: sin
        una confirmación real de `clamd`, el archivo se rechaza (503),
        nunca se sube en silencio sin escanear.
    """
    from app.core.config import settings

    host = settings.CLAMAV_HOST
    port = settings.CLAMAV_PORT
    timeout = settings.CLAMAV_SCAN_TIMEOUT_SECONDS

    deadline = time.monotonic() + timeout

    def _remaining_seconds() -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _ScanDeadlineExceeded()
        return remaining

    sock: Optional[socket.socket] = None
    try:
        sock = socket.create_connection((host, port), timeout=_remaining_seconds())
        sock.settimeout(_remaining_seconds())
        sock.sendall(b"zINSTREAM\0")

        for offset in range(0, len(content), _CLAMAV_CHUNK_SIZE):
            chunk = content[offset:offset + _CLAMAV_CHUNK_SIZE]
            sock.settimeout(_remaining_seconds())
            sock.sendall(struct.pack("!L", len(chunk)) + chunk)
        # Chunk de longitud 0 -- le indica a clamd que el stream terminó
        # (necesario incluso para contenido vacío: sin esto clamd espera
        # para siempre más datos y la conexión termina en timeout).
        sock.settimeout(_remaining_seconds())
        sock.sendall(struct.pack("!L", 0))

        response = b""
        while True:
            sock.settimeout(_remaining_seconds())
            data = sock.recv(4096)
            if not data:
                break
            response += data
            if response.endswith(b"\0"):
                break
    except _ScanDeadlineExceeded:
        logger.error(
            f"[Antivirus] clamd ({host}:{port}) superó el tiempo máximo TOTAL "
            f"configurado ({timeout}s) sin completar el escaneo"
        )
        raise ConnectionError(
            f"El servicio de antivirus no respondió dentro del tiempo máximo permitido ({timeout}s)"
        )
    except (OSError, socket.timeout) as e:
        logger.error(f"[Antivirus] Error de conexión con clamd ({host}:{port}): {e}")
        raise ConnectionError(
            f"No se pudo conectar con el servicio de antivirus: {e}"
        ) from e
    finally:
        if sock is not None:
            sock.close()

    if not response:
        logger.error(f"[Antivirus] clamd ({host}:{port}) cerró la conexión sin responder")
        raise ConnectionError("El servicio de antivirus no devolvió respuesta")

    # Formato de respuesta de clamd para INSTREAM (terminada en NUL):
    #   "stream: OK\0"                      -- limpio
    #   "stream: <NOMBRE_AMENAZA> FOUND\0"  -- infectado
    #   "stream: <mensaje de error>\0"      -- ej. tamaño máximo superado
    reply = response.rstrip(b"\0").decode("utf-8", errors="replace").strip()

    if reply.endswith("OK"):
        return True, None

    if "FOUND" in reply:
        threat_name = reply.split(":", 1)[-1].replace("FOUND", "").strip()
        return False, threat_name or "amenaza desconocida"

    logger.error(f"[Antivirus] Respuesta inesperada de clamd: {reply!r}")
    raise ConnectionError(f"Respuesta inesperada del servicio de antivirus: {reply}")


def upload_private_file_at_key(key: str, content: bytes, content_type: str) -> str:
    """Sube contenido al bucket PRIVADO en una key EXACTA (a diferencia de
    `upload_private_file`, que siempre genera una key nueva con uuid) --
    necesario para el cache de previews, donde la key tiene que ser
    predecible (`office_preview_key`) para poder chequear existencia antes
    de reconvertir. Sobreescribe silenciosamente si ya existía (no debería
    pasar en la práctica: el caller ya chequeó `object_exists_private`
    antes de convertir, ver `get_file_preview`).

    Raises:
        RuntimeError si MinIO no está disponible o la subida falla.
    """
    from app.core.config import settings

    client = _get_client()
    if not client:
        raise RuntimeError("El servicio de almacenamiento (MinIO) no está configurado")

    bucket = settings.MINIO_PRIVATE_BUCKET
    _ensure_private_bucket(bucket)
    clean_key = key.lstrip("/")

    try:
        client.upload_fileobj(
            io.BytesIO(content),
            bucket,
            clean_key,
            ExtraArgs={"ContentType": content_type},
        )
    except Exception as e:
        logger.error(f"[Storage] Error subiendo preview cacheada a {bucket}/{clean_key}: {e}")
        raise RuntimeError(f"Error al subir archivo: {e}")

    logger.info(f"[Storage] Subido (preview cacheada): {bucket}/{clean_key}")
    return clean_key
