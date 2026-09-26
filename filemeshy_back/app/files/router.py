"""Router de Carpetas y Archivos (Drive real de FileMeshy).

Cuatro routers montados en app/api/v1/router.py:
- `folders_router` (prefix /folders) y `files_router` (prefix /files) -- Hito 1,
  núcleo (carpetas, archivos, papelera, búsqueda), más los endpoints
  autenticados de creación/listado de shares de Hito 2 (conviven en estos dos
  routers porque cuelgan de /files/{id}/shares y /folders/{id}/shares).
- `shares_router` (prefix /shares) -- revocación de un share por su propio id.
- `public_shares_router` (prefix /public/shares) -- acceso público de solo
  lectura por token, SIN Depends(get_current_user).

Toda la lógica de negocio vive acá (armar filtros, validar ownership,
detectar ciclos, recursión de papelera, validación de descendencia de
shares) -- repository.py solo hace queries, siguiendo la convención ya usada
en notifications/access_control de este proyecto.
"""

import logging
import os
import secrets
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File as UploadFileParam,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.access_control.service import has_permission
from app.auth.service import RateLimiter, get_current_active_user, too_many_requests
from app.audit.service import log_audit
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.security import get_password_hash, verify_password
from app.shared.utils.client_ip import get_real_ip, rate_limit_ip_key
from app.files.models import File as FileModel, FileVersion, Folder, Share
from app.files.repository import (
    file_content_index_repo,
    file_repo,
    file_version_repo,
    folder_repo,
    share_repo,
)
from app.files.schemas import (
    BreadcrumbItem,
    CopyRequest,
    DirectoryListing,
    DownloadUrlResponse,
    FileIndexStatusOut,
    FileOut,
    FileUpdate,
    FileVersionOut,
    FolderCreate,
    FolderDetail,
    FolderOut,
    FolderUpdate,
    PreviewUrlResponse,
    PublicDownloadResponse,
    PublicFileShareOut,
    PublicFolderShareOut,
    ShareCreate,
    ShareOut,
    TagIdsUpdate,
)
from app.files.service import (
    convert_office_to_pdf,
    copy_private_object,
    delete_private_file,
    detect_audio_type,
    detect_image_type,
    detect_video_type,
    generate_presigned_url,
    is_pdf_content,
    object_exists_private,
    office_preview_key,
    scan_for_malware,
    upload_private_file,
    upload_private_file_at_key,
)
from app.storage_quota.service import reserve_upload_bytes, release_upload_bytes
from app.tags.models import Tag
from app.tags.repository import tag_repo
from app.users.models import User
from app.users.repository import user as user_repo

logger = logging.getLogger(__name__)

folders_router = APIRouter()
files_router = APIRouter()
shares_router = APIRouter()
public_shares_router = APIRouter()

# Tipos MIME verificados por contenido real (magic bytes, ver upload_file) que
# se sirven SIN forzar `attachment` -- permiten preview inline (imagen en
# <img>, PDF en <iframe>, video/audio en <video>/<audio>). Cualquier otro
# tipo, SVG incluido a propósito (es XML, puede llevar <script> embebido y
# ejecuta igual que HTML), sigue forzando `attachment` como todo el resto de
# Hito 1. Video/audio (Ronda 5) agregados con el MISMO criterio: solo se
# marcan así los formatos que `_resolve_verified_content_type` puede
# confirmar por contenido real, nunca por el Content-Type declarado.
INLINE_SAFE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
    "video/mp4",
    "video/webm",
    "video/ogg",
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
}

_VERIFIED_IMAGE_MIME_BY_FORMAT = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}

# Documentos Office que requieren conversión a PDF para poder previsualizarse
# (Ronda 5) -- ver `get_file_preview`. Los legacy (.doc/.xls/.ppt, formato
# binario OLE2 preinternet) se incluyen porque el mismo conversor los acepta
# igual que los .docx/.xlsx/.pptx modernos (XML/zip) -- es el conversor el
# que hace el trabajo pesado, acá solo se decide SI hace falta convertir.
OFFICE_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",        # .xlsx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
    "application/msword",             # .doc (legacy)
    "application/vnd.ms-excel",       # .xls (legacy)
    "application/vnd.ms-powerpoint",  # .ppt (legacy)
}

# Mismo límite que `MAX_UPLOAD_BYTES` en `filemeshy_office_converter/server.py`
# (hardcodeado ahí también -- son dos proyectos/imágenes Docker separados sin
# config compartida, así que hay que mantenerlos sincronizados a mano si
# alguno cambia). El backend tiene que rechazar ANTES de leer el objeto
# completo de MinIO y reenviarlo -- sin este chequeo, un archivo de 63MB
# viaja completo por la red interna en CADA pedido de preview, el conversor
# lo rechaza igual (con su propio límite de 50MB), y como nunca se llega a
# cachear nada el costo se repite en cada intento (hallazgo MEDIO de la
# revisión adversarial, Ronda 5: confirmado en vivo midiendo `rx_bytes` del
# contenedor `office_converter`).
MAX_OFFICE_PREVIEW_SOURCE_BYTES = 50 * 1024 * 1024

# Throttle de conversiones Office por USUARIO autenticado (no por IP -- acá
# siempre hay un `current_user` real, a diferencia de los shares públicos).
# `office_converter` es una única instancia compartida por todo el backend
# con recursos acotados (1 CPU / 1GB / 128 pids, ver docker-compose.yml) --
# sin este límite, cualquier usuario con `files.download` (el rol USER por
# defecto ya lo tiene) puede pedir preview de un Office en loop y monopolizar
# esa única instancia, degradando el preview de todos los demás (segunda
# mitad del hallazgo MEDIO de la revisión adversarial de Ronda 5). 15
# conversiones/minuto es generoso para uso real (nadie necesita convertir un
# documento nuevo cada 4 segundos navegando a mano) pero acota el abuso.
OFFICE_PREVIEW_RATE_LIMIT_MAX_CONVERSIONS = 15
OFFICE_PREVIEW_RATE_LIMIT_WINDOW_SECONDS = 60


def _enforce_office_preview_rate_limit(current_user: User) -> None:
    """Throttle por usuario de las conversiones Office->PDF, reusando la
    misma infraestructura de Redis que ya usa `/auth/login` y los shares
    públicos (`RateLimiter`, ver `_enforce_public_share_rate_limit` más
    abajo para el mismo patrón). Deliberadamente NO se aplica a todo
    `GET /files/{id}/preview` -- un cache hit o un tipo ya inline-safe no le
    cuesta nada a `office_converter`, solo el camino que realmente dispara
    una conversión nueva debe contar contra este cupo."""
    rl_key = f"office_preview:{current_user.id}"
    is_allowed, rl_message = RateLimiter.check_rate_limit(
        rl_key,
        max_attempts=OFFICE_PREVIEW_RATE_LIMIT_MAX_CONVERSIONS,
        lock_duration=OFFICE_PREVIEW_RATE_LIMIT_WINDOW_SECONDS,
    )
    if not is_allowed:
        raise too_many_requests(rl_message)
    RateLimiter.record_attempt(rl_key, window_seconds=OFFICE_PREVIEW_RATE_LIMIT_WINDOW_SECONDS)


def _audit_download(
    db: Session,
    request: Request,
    *,
    user_id,
    user_email: Optional[str],
    file_id,
    file_name: str,
    via: str,
    share_id=None,
) -> None:
    """Registra una fila de auditoría `DOWNLOAD` sobre `files`. Se llama
    DESPUÉS de generar la URL con éxito (los 404/403 no llegan acá). Nunca
    rompe la descarga: `log_audit` captura sus propios errores. La IP es la
    real (respeta TRUSTED_PROXY_IPS). NO se audita el preview."""
    new_data = {"name": file_name, "via": via}
    if share_id is not None:
        new_data["share_id"] = str(share_id)
    log_audit(
        db,
        request=request,
        user_id=str(user_id) if user_id is not None else None,
        user_email=user_email,
        action="DOWNLOAD",
        table_name="files",
        record_id=str(file_id),
        new_data=new_data,
        ip_address=get_real_ip(request),
    )


def _resolve_verified_content_type(content: bytes, declared_content_type: str) -> str:
    """Determina el Content-Type REAL a persistir, verificando el contenido
    por magic bytes -- nunca confiar en el que declaró el cliente para
    decidir después si se sirve inline (ver `_download_disposition`). Extraído
    de `_validate_and_store_upload`/`_create_new_file_version` (Ronda 5:
    mismo criterio, ahora también para video/audio, en los dos puntos donde
    se sube contenido nuevo -- versión 1 o posteriores).

    El contenedor Ogg es el único caso ambiguo (`detect_video_type`/
    `detect_audio_type` devuelven 'ogg' los dos para el mismo contenido,
    ver su docstring en service.py) -- se respeta lo que el propio cliente
    declaró (`video/ogg` explícito), y se asume `audio/ogg` en cualquier
    otro caso (uso históricamente más común de ese contenedor)."""
    detected_image = detect_image_type(content)
    if detected_image in _VERIFIED_IMAGE_MIME_BY_FORMAT:
        return _VERIFIED_IMAGE_MIME_BY_FORMAT[detected_image]

    if is_pdf_content(content):
        return "application/pdf"

    video_fmt = detect_video_type(content)
    if video_fmt == "mp4":
        return "video/mp4"
    if video_fmt == "webm":
        return "video/webm"

    audio_fmt = detect_audio_type(content)
    if audio_fmt == "mpeg":
        return "audio/mpeg"
    if audio_fmt == "wav":
        return "audio/wav"

    if video_fmt == "ogg" or audio_fmt == "ogg":
        return "video/ogg" if declared_content_type == "video/ogg" else "audio/ogg"

    if declared_content_type in INLINE_SAFE_MIME_TYPES:
        # El cliente declaró uno de los tipos "seguros para inline" pero el
        # contenido real no lo confirma -- degradar a un tipo genérico para
        # que _download_disposition nunca lo sirva inline solo por el nombre
        # del Content-Type declarado (mismo vector que motivó este chequeo
        # para imágenes, ver hallazgo crítico de Hito 2, 2026-09-06).
        return "application/octet-stream"

    return declared_content_type

# Límite de profundidad de anidamiento de carpetas (raíz = profundidad 1).
# Sin este límite, un usuario puede crear decenas de miles de carpetas
# anidadas (nada más se lo impide) y cada operación recursiva sobre ese árbol
# (move/delete/restore) se vuelve cada vez más cara -- DoS práctico del pool
# de conexiones si varios usuarios lo hacen a la vez.
MAX_FOLDER_DEPTH = 20


# ============================================================
# HELPERS INTERNOS -- ownership, breadcrumb, ciclos
# ============================================================

def _is_admin(user: User) -> bool:
    """ADMIN/SUPER_ADMIN pueden acceder y gestionar cualquier archivo o carpeta
    puntual por ID (incluida la papelera de otro usuario), pero el listado de
    raíz y la búsqueda quedan scopeados al propio usuario -- no hay (todavía)
    una vista de "explorador completo" cross-usuario para admin, eso queda
    fuera de este hito."""
    return bool(user.role_obj and user.role_obj.name in ("ADMIN", "SUPER_ADMIN"))


def _sanitize_header_value(value: str) -> str:
    """Elimina saltos de línea de un valor que va a un header HTTP
    (Content-Disposition) -- el `name` del archivo es texto libre del usuario
    y nunca debe permitir inyección de headers."""
    return value.replace("\r", "").replace("\n", "")


def _download_disposition(file_obj: FileModel, *, force: bool = False) -> Optional[str]:
    """Content-Disposition a forzar en una URL firmada de descarga/preview, o
    `None` para no forzar nada y dejar que el navegador renderice inline (el
    Content-Type verificado en upload_file ya viaja con el objeto en MinIO).

    Solo entran al allowlist los tipos que `upload_file` verificó por
    contenido real (magic bytes) -- nunca el Content-Type que declaró el
    cliente al subir, que es texto libre controlado por el atacante (ver
    hallazgo crítico de la ronda de feedback de Hito 2, 2026-09-06: sin este
    chequeo, un .html/.svg declarado como imagen se servía inline y
    ejecutaba). Cualquier tipo fuera del allowlist (SVG incluido a propósito)
    sigue forzando `attachment` como todo el resto del módulo.

    `force=True` (botón "Descargar" explícito de la UI, vía ?force_download=true)
    fuerza attachment SIN IMPORTAR el tipo -- incluso para los tipos "seguros"
    que por defecto se sirven inline para que el preview (PreviewModal) funcione.
    No cambia qué se considera "seguro", solo qué disposition se manda cuando
    el caller pide explícitamente bajar el archivo en vez de previsualizarlo."""
    safe_name = _sanitize_header_value(file_obj.name)
    if force:
        return f'attachment; filename="{safe_name}"'
    if file_obj.mime_type in INLINE_SAFE_MIME_TYPES:
        return None
    return f'attachment; filename="{safe_name}"'


def _get_owned_folder(db: Session, folder_id: UUID, current_user: User, *, active_only: bool) -> Folder:
    """Busca una carpeta por id verificando ownership. 404 si no existe, está
    fuera de alcance del usuario, o (si `active_only`) está en la papelera."""
    folder = folder_repo.get(db, folder_id)
    if not folder or (active_only and folder.deleted_at is not None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carpeta no encontrada")
    if not _is_admin(current_user) and folder.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carpeta no encontrada")
    return folder


def _get_owned_file(db: Session, file_id: UUID, current_user: User, *, active_only: bool) -> FileModel:
    file_obj = file_repo.get(db, file_id)
    if not file_obj or (active_only and file_obj.deleted_at is not None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado")
    if not _is_admin(current_user) and file_obj.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado")
    return file_obj


def _share_to_out(share: Share, *, with_resource_info: bool = False) -> ShareOut:
    """`is_active` no es una columna real -- se calcula acá, un solo lugar,
    para que todas las rutas que devuelven ShareOut (crear, listar por
    archivo/carpeta, `with-me`) usen siempre el mismo criterio.

    `shared_with_email` sale de la relación `Share.shared_with` (lazy select
    sobre la misma sesión de la request) -- evita una query aparte para el
    caso común (share público, sin destinatario).

    `with_resource_info=True` (solo lo usa `list_shares_with_me`) resuelve
    ADEMÁS `resource_name`/`resource_type` (vía `Share.file`/`Share.folder`)
    y `shared_by_email` (vía `Share.created_by`) -- mismo mecanismo lazy-select
    que `shared_with_email`. Es opt-in y no el default porque los otros
    callers (crear un share, listar los shares DE un archivo/carpeta propio)
    ya conocen el recurso y a sí mismos por contexto; resolver estas tres
    relaciones ahí sería trabajo de más sin ningún consumidor real. Si el
    recurso ya no existe (fila borrada -- no debería pasar, `Share` tiene
    `ondelete=CASCADE`) o el `created_by` fue borrado, quedan en `None` en
    vez de reventar -- la UI de "compartido conmigo" no depende de esto para
    renderizar el resto de la fila."""
    now = datetime.now(timezone.utc)
    is_active = share.revoked_at is None and (share.expires_at is None or share.expires_at > now)
    shared_with_email = share.shared_with.email if share.shared_with_user_id and share.shared_with else None

    resource_name = None
    resource_type = None
    shared_by_email = None
    if with_resource_info:
        if share.file_id is not None and share.file is not None:
            resource_name = share.file.name
            resource_type = "file"
        elif share.folder_id is not None and share.folder is not None:
            resource_name = share.folder.name
            resource_type = "folder"
        if share.created_by is not None:
            shared_by_email = share.created_by.email

    return ShareOut(
        id=share.id,
        token=share.token,
        file_id=share.file_id,
        folder_id=share.folder_id,
        created_by_id=share.created_by_id,
        expires_at=share.expires_at,
        revoked_at=share.revoked_at,
        created_at=share.created_at,
        is_active=is_active,
        permission=share.permission,
        has_password=share.password_hash is not None,
        shared_with_user_id=share.shared_with_user_id,
        shared_with_email=shared_with_email,
        resource_name=resource_name,
        resource_type=resource_type,
        shared_by_email=shared_by_email,
    )


def _resolve_shared_with_user(db: Session, email: Optional[str]) -> Optional[User]:
    """Resuelve `shared_with_email` (si vino) al usuario destinatario real.
    404 claro si no existe nadie con ese email -- mismo criterio del resto
    del módulo de no dejar que una FK inválida reviente en un 500, pero acá
    SÍ se distingue el motivo (a diferencia de los helpers de ownership) por
    ser un dato que el propio usuario que comparte tipeó a mano, no un id
    adivinado por un tercero."""
    if not email:
        return None
    target_user = user_repo.get_by_email(db, email)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return target_user


def _notify_share_recipient(db: Session, recipient_id: UUID, resource_name: str) -> None:
    """Notifica al destinatario de un share dirigido recién creado (Ronda 3).
    Import diferido de `create_notification` -- mismo patrón que
    `app/storage_quota/service.py::_notify_if_near_limit`, evita un ciclo de
    import a nivel de módulo entre `files` y `worker.tasks`. `create_notification`
    ya es best-effort internamente (atrapa sus propias excepciones y devuelve
    False) -- no hace falta envolver esta llamada en otro try/except."""
    from app.notifications.routes import ACTION_URL_SHARED_WITH_ME
    from app.worker.tasks.notification_helpers import create_notification

    create_notification(
        db=db,
        user_id=recipient_id,
        title="Te compartieron un elemento",
        message=f"Te compartieron: {resource_name}",
        notif_type="compartido",
        severity="info",
        action_url=ACTION_URL_SHARED_WITH_ME,
        extra_data={},
    )


def _create_share(
    db: Session,
    *,
    file_id: Optional[UUID],
    folder_id: Optional[UUID],
    resource_name: str,
    current_user: User,
    payload: ShareCreate,
) -> Share:
    """Crea un `Share` de archivo o carpeta -- lógica común a
    `create_file_share`/`create_folder_share` (Ronda 3: password opcional,
    permission, y resolución de `shared_with_email` a un destinatario real).

    Si se resolvió un destinatario, NO se genera `token` (el acceso a un
    share dirigido es siempre autenticado, nunca por el link público) y se
    dispara una notificación al destinatario."""
    target_user = _resolve_shared_with_user(db, payload.shared_with_email)
    token = None if target_user else secrets.token_urlsafe(32)
    password_hash = get_password_hash(payload.password) if payload.password else None

    share = Share(
        file_id=file_id,
        folder_id=folder_id,
        token=token,
        created_by_id=current_user.id,
        expires_at=payload.expires_at,
        password_hash=password_hash,
        permission=payload.permission,
        shared_with_user_id=target_user.id if target_user else None,
    )
    db.add(share)
    db.commit()
    db.refresh(share)

    if target_user is not None:
        _notify_share_recipient(db, target_user.id, resource_name)

    return share


def _resolve_owned_tags(db: Session, owner_id: UUID, tag_ids: List[UUID]) -> List[Tag]:
    """Resuelve una lista de `tag_ids` a sus filas `Tag` reales, validando
    que TODAS pertenezcan a `owner_id` -- criterio "todo o nada": si algún id
    no existe o es de otro usuario, 404 en vez de aplicar en silencio el
    subconjunto válido (evita que un usuario le asigne a un archivo propio
    una etiqueta ajena adivinando/probando ids, ver test_files_tags.py).
    Deduplica preservando orden (un mismo id repetido en el body no debe
    romper la comparación de longitudes)."""
    unique_ids = list(dict.fromkeys(tag_ids))
    if not unique_ids:
        return []
    tags = tag_repo.get_by_ids_for_owner(db, owner_id, unique_ids)
    if len(tags) != len(unique_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Una o más etiquetas no existen o no pertenecen al usuario",
        )
    return tags


def _get_target_parent_folder(db: Session, parent_id: UUID, owner_id: UUID) -> Folder:
    """Valida que una carpeta destino (para crear/mover algo dentro) exista,
    esté activa y pertenezca al mismo dueño del objeto que se está moviendo --
    404 en vez de dejar que una FK inválida reviente en un 500."""
    parent = folder_repo.get_active(db, parent_id)
    if not parent or parent.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carpeta destino no encontrada")
    return parent


def _folder_depth(db: Session, folder: Folder) -> int:
    """Profundidad de `folder` contando desde la raíz -- una carpeta raíz
    (sin padre) tiene profundidad 1."""
    depth = 1
    current_parent_id = folder.parent_id
    seen = {folder.id}
    while current_parent_id is not None and current_parent_id not in seen:
        parent = folder_repo.get(db, current_parent_id)
        if not parent:
            break
        depth += 1
        seen.add(current_parent_id)
        current_parent_id = parent.parent_id
    return depth


def _would_create_cycle(db: Session, folder_id: UUID, new_parent_id: UUID) -> bool:
    """True si mover `folder_id` dentro de `new_parent_id` crearía un ciclo
    (mover una carpeta dentro de sí misma o de un descendiente propio)."""
    if new_parent_id == folder_id:
        return True
    descendant_ids = folder_repo.get_descendant_ids(db, folder_id)
    return new_parent_id in descendant_ids


def _build_ancestors(db: Session, folder: Folder) -> List[BreadcrumbItem]:
    """Ancestros de `folder` desde la raíz hasta su padre inmediato (sin
    incluir a la propia carpeta)."""
    items: List[BreadcrumbItem] = []
    seen = {folder.id}
    current_parent_id = folder.parent_id
    while current_parent_id is not None and current_parent_id not in seen:
        parent = folder_repo.get(db, current_parent_id)
        if not parent:
            break
        items.append(BreadcrumbItem(id=parent.id, name=parent.name))
        seen.add(parent.id)
        current_parent_id = parent.parent_id
    items.reverse()
    return items


def _soft_delete_folder_recursive(db: Session, folder: Folder, now: datetime) -> None:
    descendant_ids = folder_repo.get_descendant_ids(db, folder.id)
    all_folder_ids = [folder.id] + descendant_ids
    db.query(Folder).filter(Folder.id.in_(all_folder_ids)).update(
        {"deleted_at": now}, synchronize_session=False
    )
    db.query(FileModel).filter(FileModel.folder_id.in_(all_folder_ids)).update(
        {"deleted_at": now}, synchronize_session=False
    )
    db.commit()


def _restore_folder_recursive(db: Session, folder: Folder) -> None:
    """Restaura `folder` y todo su subárbol. Si el padre directo de `folder`
    sigue en la papelera (o ya no existe), la desancla a la raíz en la misma
    operación -- evita que quede huérfana e invisible colgada de un padre
    borrado (no se restaura la cadena completa de ancestros, solo se corta
    el vínculo)."""
    if folder.parent_id is not None:
        parent = folder_repo.get(db, folder.parent_id)
        if not parent or parent.deleted_at is not None:
            db.query(Folder).filter(Folder.id == folder.id).update(
                {"parent_id": None}, synchronize_session=False
            )

    descendant_ids = folder_repo.get_descendant_ids(db, folder.id)
    all_folder_ids = [folder.id] + descendant_ids
    db.query(Folder).filter(Folder.id.in_(all_folder_ids)).update(
        {"deleted_at": None}, synchronize_session=False
    )
    db.query(FileModel).filter(FileModel.folder_id.in_(all_folder_ids)).update(
        {"deleted_at": None}, synchronize_session=False
    )
    db.commit()


# ============================================================
# COPIA -- helpers compartidos por /files/{id}/copy y /folders/{id}/copy
# ============================================================

def _read_private_object(storage_key: str) -> bytes:
    """Lee el contenido crudo de un objeto del bucket privado de MinIO
    directo por el cliente S3 interno (mismo cliente que usa `upload_private_file`),
    en vez de generar una URL firmada e ir por HTTP -- una URL firmada por
    `generate_presigned_url` apunta a `MINIO_PUBLIC_URL` (pensado para que la
    resuelva el navegador del usuario), que no necesariamente es alcanzable
    desde DENTRO del propio contenedor del backend."""
    from app.files.service import _get_client  # helper interno del módulo, ver su docstring

    client = _get_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="El servicio de almacenamiento no está disponible",
        )
    try:
        obj = client.get_object(Bucket=settings.MINIO_PRIVATE_BUCKET, Key=storage_key)
        return obj["Body"].read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo leer el archivo original",
        ) from e


def _enqueue_content_indexing(file_id: UUID) -> None:
    """Encola la extracción de texto/OCR del contenido ACTUAL de `file_id`
    (Ronda 6: búsqueda por contenido) -- best-effort y asíncrono, nunca
    bloquea la respuesta del endpoint que la dispara ni la revienta si
    Celery/Redis no están disponibles en este momento (mismo criterio que
    `_notify_share_recipient`: encolar una tarea no es parte del contrato
    síncrono de estos endpoints). Import diferido -- mismo motivo que el
    resto del módulo evita imports de `app.worker.tasks.*` a nivel de
    archivo (ciclo de import entre `files` y `worker.tasks`).

    Se llama en los CUATRO puntos donde el contenido de un archivo puede
    cambiar: subida inicial (`_validate_and_store_upload`, cubre tanto
    `upload_file` como `upload_file_via_share`), versión nueva
    (`_create_new_file_version`, cubre tanto `upload_file_version` como
    `replace_file_via_share`), y restauración de una versión vieja
    (`restore_file_version`)."""
    try:
        from app.core.database import tenant_schema_ctx
        from app.worker.tasks.indexing import index_file_content

        # Nuevo encolado -> el contador de intentos (tope de redelivery)
        # arranca de cero. Best-effort: sesión propia y corta.
        try:
            reset_db = SessionLocal()
            try:
                file_content_index_repo.reset_attempts(reset_db, file_id)
            finally:
                reset_db.close()
        except Exception:
            logger.warning(f"No se pudo resetear attempts de indexación de {file_id}", exc_info=True)

        index_file_content.delay(tenant_schema_ctx.get(), str(file_id))
    except Exception:
        logger.warning(f"No se pudo encolar la indexación de contenido de {file_id}", exc_info=True)


def _copy_with_suffix(name: str, *, same_location: bool) -> str:
    """Nombre de una copia: si el destino es el mismo lugar que el original
    lleva el sufijo " (copia)" (para no chocar con el nombre existente); si
    el destino es otro lugar, se conserva el nombre tal cual. Trunca la base
    si hiciera falta para no superar `String(255)` de la columna `name`."""
    if not same_location:
        return name
    suffix = " (copia)"
    if len(name) + len(suffix) > 255:
        name = name[: 255 - len(suffix)]
    return name + suffix


def _resolve_copy_destination(
    db: Session,
    owner_id: UUID,
    default_parent_id: Optional[UUID],
    payload: Optional[CopyRequest],
) -> Optional[UUID]:
    """Resuelve el `folder_id` destino de una copia. Si el cliente no mandó
    el campo (body ausente o `{}`), el destino es `default_parent_id` (el
    mismo lugar que el original) -- si lo mandó explícito (incluido `null`),
    se respeta tal cual. `null` explícito = raíz. Un UUID puntual se valida
    con el mismo helper de ownership que usa el resto del router (404 si no
    existe o es de otro dueño)."""
    if payload is not None and payload.to_root:
        return None
    if payload is not None and "folder_id" in payload.model_fields_set:
        if payload.folder_id is None:
            return None
        target = _get_target_parent_folder(db, payload.folder_id, owner_id)
        return target.id
    return default_parent_id


def _reserve_copy_quota(owner_id: UUID, size: int) -> None:
    """Reserva cuota para un archivo copiado, en una sesión de DB PROPIA --
    NUNCA la sesión de la request.

    `reserve_upload_bytes`/`release_upload_bytes` hacen su propio `db.commit()`
    atómico (ver storage_quota/service.py) -- si compartieran la sesión de la
    request, ese commit finalizaría TAMBIÉN cualquier Folder/File que la copia
    recursiva ya haya agregado con `db.flush()` pero que todavía no debería
    quedar permanente (se necesita `flush` sin commit para conocer el `id`
    del Folder padre antes de crear sus hijos). Confirmado en vivo con un
    smoke test manual: sin este aislamiento, una copia de carpeta que falla a
    mitad de camino (ej. cuota agotada en el segundo archivo) dejaba la
    carpeta ya creada a pesar del `db.rollback()` posterior, porque la
    reserva de cuota del PRIMER archivo ya había comprometido esa fila."""
    quota_db = SessionLocal()
    try:
        reserve_upload_bytes(quota_db, owner_id, size)
    finally:
        quota_db.close()


def _release_copy_quota(owner_id: UUID, size: int) -> None:
    """Compensa `_reserve_copy_quota` -- misma razón de sesión propia."""
    quota_db = SessionLocal()
    try:
        release_upload_bytes(quota_db, owner_id, size)
    finally:
        quota_db.close()


def _rollback_copy(db: Session, reservations: List[tuple], uploaded_keys: List[str]) -> None:
    """Compensa una copia (de archivo o de carpeta completa) que falló a
    mitad de camino: libera toda cuota ya reservada, borra todo objeto ya
    subido a MinIO, y descarta las filas de File/Folder todavía sin commit
    (gracias a que la cuota se reserva en una sesión aparte, ver
    `_reserve_copy_quota`, este `rollback` sí las descarta de verdad)."""
    for owner_id, size in reservations:
        _release_copy_quota(owner_id, size)
    for key in uploaded_keys:
        delete_private_file(key)
    db.rollback()


def _copy_file_object(
    db: Session,
    source_file: FileModel,
    *,
    owner_id: UUID,
    folder_id: Optional[UUID],
    name: str,
    reservations: List[tuple],
    uploaded_keys: List[str],
    created_ids: Optional[List[UUID]] = None,
) -> FileModel:
    """Copia un único archivo (bytes + fila nueva), reservando cuota real
    igual que `upload_file`. No hace `commit` -- lo hace el caller una vez
    que terminó (todo el archivo, o todo el subárbol de una carpeta)."""
    # Ronda 12d: la copia NO trae el contenido al proceso (copia server-side en MinIO) y no
    # se debilita el escaneo antivirus: solo se copia un archivo 'clean' (los pending/
    # infected/scan_failed ni siquiera son visibles por el CRUD, esto es defensa en profundidad)
    # y la copia hereda el `scan_status` del origen, nunca queda "clean" por defecto.
    if source_file.scan_status != "clean":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El archivo todavía no pasó el análisis antivirus: no se puede copiar",
        )
    size = source_file.size_bytes or 0

    _reserve_copy_quota(owner_id, size)
    reservations.append((owner_id, size))

    try:
        storage_key = copy_private_object(
            source_file.storage_key,
            dest_path=f"files/{owner_id}",
            extension=os.path.splitext(source_file.name)[1],
            content_type=source_file.mime_type,
        )
    except Exception:
        _release_copy_quota(owner_id, size)
        reservations.pop()
        raise
    uploaded_keys.append(storage_key)

    new_file = FileModel(
        name=name,
        folder_id=folder_id,
        owner_id=owner_id,
        storage_key=storage_key,
        size_bytes=size,
        mime_type=source_file.mime_type,
        scan_status=source_file.scan_status,
    )
    db.add(new_file)
    db.flush()
    # Versión inicial (igual que una subida normal): sin ella la copia no tenía historial.
    db.add(
        FileVersion(
            file_id=new_file.id,
            version_number=1,
            storage_key=storage_key,
            size_bytes=size,
            mime_type=source_file.mime_type,
            created_by_id=owner_id,
        )
    )
    db.flush()
    if created_ids is not None:
        created_ids.append(new_file.id)
    return new_file


def _copy_folder_tree(
    db: Session,
    source_folder: Folder,
    *,
    owner_id: UUID,
    parent_id: Optional[UUID],
    name: str,
    reservations: List[tuple],
    uploaded_keys: List[str],
    created_ids: Optional[List[UUID]] = None,
) -> Folder:
    """Copia recursiva de `source_folder` (la carpeta en sí + todo su
    subárbol de subcarpetas y archivos activos) bajo `parent_id`. La
    profundidad máxima ya se validó ANTES de llamar a esto (ver
    `copy_folder`) -- acá solo se recorre y se copia."""
    new_folder = Folder(name=name, parent_id=parent_id, owner_id=owner_id)
    db.add(new_folder)
    db.flush()

    for child_file in file_repo.get_children(db, source_folder.owner_id, source_folder.id):
        _copy_file_object(
            db,
            child_file,
            owner_id=owner_id,
            folder_id=new_folder.id,
            name=child_file.name,
            reservations=reservations,
            uploaded_keys=uploaded_keys,
            created_ids=created_ids,
        )

    for child_folder in folder_repo.get_children(db, source_folder.owner_id, source_folder.id):
        _copy_folder_tree(
            db,
            child_folder,
            owner_id=owner_id,
            parent_id=new_folder.id,
            name=child_folder.name,
            reservations=reservations,
            uploaded_keys=uploaded_keys,
            created_ids=created_ids,
        )

    return new_folder


# ============================================================
# FOLDERS
# ============================================================

@folders_router.post("", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
def create_folder(
    payload: FolderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["folders.create"])),
):
    if payload.parent_id is not None:
        parent = _get_target_parent_folder(db, payload.parent_id, current_user.id)
        if _folder_depth(db, parent) + 1 > MAX_FOLDER_DEPTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profundidad máxima de carpetas alcanzada",
            )

    folder = Folder(name=payload.name, parent_id=payload.parent_id, owner_id=current_user.id)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


@folders_router.get("/{folder_id}", response_model=FolderDetail)
def get_folder(
    folder_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["folders.view"])),
):
    folder = _get_owned_folder(db, folder_id, current_user, active_only=True)
    ancestors = _build_ancestors(db, folder)
    data = FolderOut.model_validate(folder).model_dump()
    return FolderDetail(**data, breadcrumb=ancestors)


@folders_router.patch("/{folder_id}", response_model=FolderOut)
def update_folder(
    folder_id: UUID,
    payload: FolderUpdate,
    db: Session = Depends(get_db),
    # Gate de la dependency bajado a "folders.view" (lo tiene el rol USER por
    # defecto) -- "folders.rename"/"folders.move" se siguen exigiendo
    # EXPLÍCITAMENTE más abajo, campo por campo, cuando "name"/"parent_id"
    # vienen seteados. Marcar/desmarcar favorito es una preferencia personal
    # sobre un recurso que ya se valida por ownership (_get_owned_folder) --
    # no debería exigir el mismo permiso que renombrar o mover (hallazgo del
    # auditor final de Ronda 1, 2026-09-20: con el gate viejo, el rol USER
    # por defecto no podía favoritear nada, el caso de uso principal de esta
    # ronda quedaba inutilizable para cualquiera sin folders.rename/move).
    current_user: User = Depends(has_permission(["folders.view"])),
):
    folder = _get_owned_folder(db, folder_id, current_user, active_only=True)
    fields_set = payload.model_fields_set
    is_admin = _is_admin(current_user)
    user_perms = current_user.permissions or []

    if "name" in fields_set:
        if not (is_admin or "folders.rename" in user_perms):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tiene permiso para renombrar carpetas")
        if payload.name is not None:
            folder.name = payload.name

    if "parent_id" in fields_set:
        if not (is_admin or "folders.move" in user_perms):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tiene permiso para mover carpetas")
        new_parent_id = payload.parent_id
        if new_parent_id is not None:
            if _would_create_cycle(db, folder.id, new_parent_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No se puede mover una carpeta dentro de sí misma o de uno de sus descendientes",
                )
            target_parent = _get_target_parent_folder(db, new_parent_id, folder.owner_id)
            subtree_height = folder_repo.get_subtree_height(db, folder.id)
            if _folder_depth(db, target_parent) + 1 + subtree_height > MAX_FOLDER_DEPTH:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Profundidad máxima de carpetas alcanzada",
                )
        folder.parent_id = new_parent_id

    if "is_favorite" in fields_set and payload.is_favorite is not None:
        folder.is_favorite = payload.is_favorite

    db.commit()
    db.refresh(folder)
    return folder


@folders_router.put("/{folder_id}/tags", response_model=FolderOut)
def set_folder_tags(
    folder_id: UUID,
    payload: TagIdsUpdate,
    db: Session = Depends(get_db),
    # Mismo gate que update_folder (folders.view, no folders.rename/move) --
    # taggear es una preferencia personal de organización sobre un recurso
    # ya validado por ownership, no una operación de bajo riesgo asimilable
    # a renombrar/mover (mismo criterio que is_favorite, ver comentario de
    # update_folder más arriba -- no repetir el bug corregido en Ronda 1).
    current_user: User = Depends(has_permission(["folders.view"])),
):
    """Reemplaza el set COMPLETO de etiquetas de la carpeta (no incremental).
    Todos los `tag_ids` deben pertenecer al usuario dueño de la carpeta --
    ver `_resolve_owned_tags`."""
    folder = _get_owned_folder(db, folder_id, current_user, active_only=True)
    folder.tags = _resolve_owned_tags(db, folder.owner_id, payload.tag_ids)
    db.commit()
    db.refresh(folder)
    return folder


@folders_router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(
    folder_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["folders.delete"])),
):
    folder = _get_owned_folder(db, folder_id, current_user, active_only=True)
    now = datetime.now(timezone.utc)
    _soft_delete_folder_recursive(db, folder, now)
    return None


@folders_router.post("/{folder_id}/restore", response_model=FolderOut)
def restore_folder(
    folder_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["folders.delete"])),
):
    folder = _get_owned_folder(db, folder_id, current_user, active_only=False)
    if folder.deleted_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La carpeta no está en la papelera")
    _restore_folder_recursive(db, folder)
    db.refresh(folder)
    return folder


@folders_router.post("/{folder_id}/copy", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
def copy_folder(
    folder_id: UUID,
    payload: Optional[CopyRequest] = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.upload"])),
):
    """Copia recursiva de una carpeta y todo su contenido activo (subcarpetas
    + archivos). Requiere `files.upload` -- mismo criterio que copiar un
    archivo: copiar una carpeta consume cuota real por cada archivo que
    arrastra, ni más ni menos que subirlos de nuevo uno por uno.

    Ownership del origen validado por `_get_owned_folder` (mismo patrón que
    el resto del router). El destino, si se pasa explícito, se valida con
    `_get_target_parent_folder` dentro de `_resolve_copy_destination` --
    nunca se copia hacia una carpeta de otro dueño."""
    source_folder = _get_owned_folder(db, folder_id, current_user, active_only=True)

    dest_parent_id = _resolve_copy_destination(db, source_folder.owner_id, source_folder.parent_id, payload)

    if dest_parent_id is not None:
        dest_parent = folder_repo.get(db, dest_parent_id)
        if not dest_parent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carpeta destino no encontrada")
        # Ronda 12c (MEDIO-4): copiar una carpeta dentro de sí misma o de un descendiente
        # es un ciclo (reproducido: 500 por recursión sobre la copia recién flusheada,
        # con rollback dejando objetos de storage huérfanos). Se rechaza ANTES de copiar
        # nada, con el mismo helper que usa mover.
        if _would_create_cycle(db, source_folder.id, dest_parent_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede copiar una carpeta dentro de sí misma ni de una de sus subcarpetas",
            )
        dest_parent_depth = _folder_depth(db, dest_parent)
    else:
        dest_parent_depth = 0

    # Misma fórmula que valida update_folder al mover un subárbol completo
    # (ver arriba): profundidad del destino + 1 (la carpeta copiada en sí) +
    # la altura de su propio subárbol no puede superar MAX_FOLDER_DEPTH.
    subtree_height = folder_repo.get_subtree_height(db, source_folder.id)
    if dest_parent_depth + 1 + subtree_height > MAX_FOLDER_DEPTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profundidad máxima de carpetas alcanzada",
        )

    same_location = dest_parent_id == source_folder.parent_id
    new_name = _copy_with_suffix(source_folder.name, same_location=same_location)

    reservations: List[tuple] = []
    uploaded_keys: List[str] = []
    created_ids: List[UUID] = []
    try:
        new_folder = _copy_folder_tree(
            db,
            source_folder,
            owner_id=source_folder.owner_id,
            parent_id=dest_parent_id,
            name=new_name,
            reservations=reservations,
            uploaded_keys=uploaded_keys,
            created_ids=created_ids,
        )
        db.commit()
    except Exception:
        _rollback_copy(db, reservations, uploaded_keys)
        raise
    db.refresh(new_folder)
    for new_id in created_ids:  # cada archivo copiado se re-indexa
        _enqueue_content_indexing(new_id)
    return new_folder


# ============================================================
# FILES
# ============================================================

@files_router.get("", response_model=DirectoryListing)
def list_directory(
    folder_id: Optional[UUID] = Query(None),
    q: Optional[str] = Query(None),
    trash: bool = Query(False),
    sort_by: str = Query("name"),
    sort_dir: str = Query("asc"),
    favorites_only: bool = Query(False),
    tag_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.view"])),
):
    if q:
        folders = folder_repo.search(db, current_user.id, q, sort_by, sort_dir, favorites_only, tag_id)
        files = file_repo.search(db, current_user.id, q, sort_by, sort_dir, favorites_only, tag_id)
        return DirectoryListing(folders=folders, files=files, breadcrumb=[])

    if trash:
        # Sin vista fusionada cross-usuario, igual criterio que el listado raíz y la búsqueda de
        # arriba: admin accede a recursos puntuales por ID (ver _get_owned_folder/_get_owned_file),
        # no ve la papelera ajena solo por tener rol admin (hallazgo del auditor final, 2026-09-05).
        owner_filter = current_user.id
        folders = folder_repo.get_trash(db, owner_filter, sort_by, sort_dir, favorites_only, tag_id)
        files = file_repo.get_trash(db, owner_filter, sort_by, sort_dir, favorites_only, tag_id)
        return DirectoryListing(folders=folders, files=files, breadcrumb=[])

    breadcrumb: List[BreadcrumbItem] = []
    if folder_id is not None:
        folder = _get_owned_folder(db, folder_id, current_user, active_only=True)
        breadcrumb = _build_ancestors(db, folder) + [BreadcrumbItem(id=folder.id, name=folder.name)]
        owner_scope = folder.owner_id
    else:
        owner_scope = current_user.id

    folders = folder_repo.get_children(db, owner_scope, folder_id, sort_by, sort_dir, favorites_only, tag_id)
    files = file_repo.get_children(db, owner_scope, folder_id, sort_by, sort_dir, favorites_only, tag_id)
    return DirectoryListing(folders=folders, files=files, breadcrumb=breadcrumb)


async def _scan_for_malware_or_raise(content: bytes, *, original_name: str) -> None:
    """Escanea `content` contra ClamAV real y aborta la request si
    corresponde -- política fail-closed (Ronda 7): NUNCA se sube nada a
    MinIO sin una confirmación real de `clamd` (ver `scan_for_malware` en
    service.py).

    - Infectado -> 422, mensaje con el nombre de la amenaza detectada.
    - `clamd` no responde/falla la conexión -> 503. Deliberadamente NO se
      interpreta como "está limpio" -- lo contrario dejaría pasar CUALQUIER
      archivo sin escanear con solo tirar abajo (o saturar) el contenedor
      `clamav`, exactamente el escenario que este chequeo existe para
      prevenir.

    `scan_for_malware` es bloqueante de verdad (sockets crudos sin async,
    ver service.py) y puede tardar segundos con un archivo grande -- se
    corre en el threadpool de Starlette (`run_in_threadpool`), NUNCA
    directo en el loop de asyncio. Confirmado en vivo por la revisión
    adversarial (Ronda 7): sin esto, un upload de 90MB con ~2.15s de
    escaneo real hacía que un `GET /files` CONCURRENTE de otro usuario
    pasara de 0.02s a 1.83s -- con uvicorn sin `--workers`, el escaneo de
    UN usuario congelaba el backend para TODOS.

    Compartido por `_validate_and_store_upload`/`_create_new_file_version`
    -- los DOS únicos lugares donde content nuevo entra al sistema, que en
    conjunto cubren los CUATRO endpoints de subida (`upload_file`,
    `upload_file_via_share`, `upload_file_version`, `replace_file_via_share`).
    Se llama ANTES de reservar cuota y ANTES de subir a MinIO en los dos
    casos."""
    try:
        is_clean, threat_name = await run_in_threadpool(scan_for_malware, content)
    except ConnectionError as e:
        logger.error(
            f"[Antivirus] Servicio de antivirus no disponible escaneando '{original_name}': {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de antivirus no disponible, intentá más tarde",
        )

    if not is_clean:
        logger.warning(
            f"[Antivirus] Archivo '{original_name}' rechazado -- amenaza detectada: {threat_name}"
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Archivo rechazado: se detectó contenido malicioso ({threat_name})",
        )


async def _validate_and_store_upload(
    db: Session,
    *,
    owner_id: UUID,
    folder_id: Optional[UUID],
    upload: UploadFile,
    content: bytes,
    created_by_id: UUID,
) -> FileModel:
    """Valida el contenido real de un upload (magic bytes) y lo persiste:
    reserva de cuota contra `owner_id`, subida a MinIO, la fila `File`
    resultante y su `FileVersion` 1 (Ronda 4: un archivo SIEMPRE tiene al
    menos una versión, la del upload original). Extraído de `upload_file`
    (Hito 1) para reusarlo tal cual en `upload_file_via_share` (Ronda 3: el
    destinatario de un share de carpeta con `permission='edit'` sube un
    archivo nuevo) -- MISMA verificación de tipo real y MISMO patrón de
    reserva/rollback de cuota en los dos casos.

    `created_by_id` es quien subió el archivo (no necesariamente `owner_id`
    -- en un upload vía share de carpeta, el archivo queda a nombre del
    DUEÑO de la carpeta pero lo subió el destinatario, ver
    `upload_file_via_share`).

    El caller ya validó tamaño máximo (`file.size`/`len(content)`) ANTES de
    llamar acá -- esta función asume que `content` ya está dentro del límite."""
    original_name = upload.filename or "archivo"
    if len(original_name) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre no puede superar los 255 caracteres",
        )
    _, extension = os.path.splitext(original_name)
    content_type = upload.content_type or "application/octet-stream"

    # Verificación de tipo real por contenido (magic bytes), NUNCA confiar en
    # el Content-Type que declara el cliente para decidir si un archivo se
    # puede servir inline más adelante (ver _download_disposition) -- lo
    # declarado es texto libre controlado por el atacante. Si el contenido
    # real es una imagen (nunca SVG: es XML, puede llevar <script> embebido
    # y ejecuta igual que HTML), un PDF, o video/audio real (Ronda 5), se
    # sobreescribe `content_type` con el verificado -- ver
    # `_resolve_verified_content_type`.
    content_type = _resolve_verified_content_type(content, content_type)

    # Ronda 7: escaneo de malware (ClamAV) -- ANTES de reservar cuota y de
    # subir nada a MinIO. Ver `_scan_for_malware_or_raise` para la política
    # fail-closed completa (y por qué esta función pasó a ser `async` --
    # el escaneo corre en threadpool, nunca bloqueante en el loop).
    await _scan_for_malware_or_raise(content, original_name=original_name)

    # Cuota de almacenamiento del DUEÑO real (`owner_id`) -- en un upload vía
    # share (Ronda 3) puede no ser `current_user`, ver `upload_file_via_share`.
    # Chequeo y reserva son la MISMA operación atómica (UPDATE con guard, ver
    # app/storage_quota/service.py::reserve_upload_bytes), ANTES de subir a
    # MinIO -- separar "chequear" de "sumar" en dos pasos dejaba una ventana
    # donde dos uploads concurrentes del mismo usuario, cada uno por debajo
    # del remanente, pasaban el chequeo por separado y sumados superaban el
    # límite (hallazgo de la revisión adversarial, Fase 3, 2026-09-08).
    reserve_upload_bytes(db, owner_id, len(content))

    try:
        storage_key = upload_private_file(
            path=f"files/{owner_id}",
            content=content,
            extension=extension,
            content_type=content_type,
        )
    except Exception:
        # La reserva de arriba ya sumó a bytes_used -- si la subida a MinIO
        # falla, hay que liberarla o el contador queda inflado por un
        # archivo que nunca llegó a existir.
        release_upload_bytes(db, owner_id, len(content))
        raise

    db_file = FileModel(
        name=original_name,
        folder_id=folder_id,
        owner_id=owner_id,
        storage_key=storage_key,
        size_bytes=len(content),
        mime_type=content_type,
    )
    db.add(db_file)
    db.flush()

    db.add(
        FileVersion(
            file_id=db_file.id,
            version_number=1,
            storage_key=storage_key,
            size_bytes=len(content),
            mime_type=content_type,
            created_by_id=created_by_id,
        )
    )
    db.commit()
    db.refresh(db_file)
    # Ronda 6: encolar indexación de contenido/OCR -- asíncrono, no bloquea
    # esta respuesta (ver docstring de `_enqueue_content_indexing`).
    _enqueue_content_indexing(db_file.id)
    return db_file


@files_router.post("/upload", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = UploadFileParam(...),
    folder_id: Optional[UUID] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.upload"])),
):
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    # Chequeo temprano si Starlette ya conoce el tamaño (evita leer a memoria
    # un archivo que de entrada excede el límite).
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"El archivo supera el tamaño máximo permitido ({settings.MAX_UPLOAD_SIZE_MB} MB)",
        )

    if folder_id is not None:
        # Mismo criterio que create_folder/update_file/update_folder para el
        # destino de un objeto nuevo: la carpeta tiene que pertenecer al
        # propio usuario, sin la excepción de admin que sí tiene
        # _get_owned_folder (esa excepción es para acceder/gestionar un
        # recurso puntual ya conocido, no para decidir el owner_scope de un
        # archivo nuevo -- si no, el archivo queda con owner_id=current_user
        # pero folder_id de otro dueño, invisible para los dos al listar).
        _get_target_parent_folder(db, folder_id, current_user.id)

    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"El archivo supera el tamaño máximo permitido ({settings.MAX_UPLOAD_SIZE_MB} MB)",
        )

    return await _validate_and_store_upload(
        db, owner_id=current_user.id, folder_id=folder_id, upload=file, content=content,
        created_by_id=current_user.id,
    )


@files_router.get("/{file_id}", response_model=FileOut)
def get_file(
    file_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.view"])),
):
    return _get_owned_file(db, file_id, current_user, active_only=True)


@files_router.get("/{file_id}/download", response_model=DownloadUrlResponse)
def download_file(
    request: Request,
    file_id: UUID,
    force_download: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.download"])),
):
    file_obj = _get_owned_file(db, file_id, current_user, active_only=True)
    disposition = _download_disposition(file_obj, force=force_download)
    url = generate_presigned_url(file_obj.storage_key, response_content_disposition=disposition)
    # Auditoría explícita de la descarga (el AuditMiddleware solo cubre
    # escrituras). Valores capturados ANTES: log_audit hace commit y puede
    # expirar los objetos ORM.
    _audit_download(
        db, request,
        user_id=current_user.id, user_email=current_user.email,
        file_id=file_obj.id, file_name=file_obj.name, via="direct",
    )
    return DownloadUrlResponse(download_url=url)


@files_router.get("/{file_id}/preview", response_model=PreviewUrlResponse)
def get_file_preview(
    file_id: UUID,
    db: Session = Depends(get_db),
    # Mismo permiso que descargar -- una preview es, en los hechos, una
    # forma de acceder al contenido del archivo.
    current_user: User = Depends(has_permission(["files.download"])),
):
    """URL lista para embeber (`<iframe>`/`<video>`/`<img>`) del preview de
    `file_id` (Ronda 5). Ownership requerido, mismo criterio que el resto
    del módulo (`_get_owned_file`).

    - Tipos ya servibles inline (imagen/PDF/video/audio verificados por
      contenido real, ver `INLINE_SAFE_MIME_TYPES`): devuelve la misma URL
      firmada que `download_file` sin forzar `attachment` -- no hace falta
      convertir nada.
    - Documentos Office (`OFFICE_MIME_TYPES`): convierte a PDF vía el
      servicio aislado `office_converter` la PRIMERA vez que se pide el
      preview de esa versión exacta del archivo, cachea el resultado en
      MinIO (`office_preview_key`, por `file_id` + `version_number`
      ACTUAL -- ver su docstring: una versión nueva o una restauración
      invalida el cache viejo solo con cambiar ese número) y sirve el
      cacheado en cualquier pedido posterior sin volver a convertir.

    Si el conversor no está disponible, tarda más de lo esperado, o
    rechaza el documento, responde 502 con un detalle apto para mostrar
    directo al usuario -- nunca un 500 crudo (ver `convert_office_to_pdf`).

    Antes de leer/reenviar nada al conversor (Ronda 5, hallazgo MEDIO de la
    revisión adversarial): rechaza fail-fast (413) un archivo más grande
    que `MAX_OFFICE_PREVIEW_SOURCE_BYTES`, y aplica un throttle por usuario
    (`_enforce_office_preview_rate_limit`) -- los dos SOLO en el camino que
    realmente dispara una conversión nueva (cache miss), nunca en un cache
    hit ni en un tipo ya inline-safe.
    """
    file_obj = _get_owned_file(db, file_id, current_user, active_only=True)

    if file_obj.mime_type not in OFFICE_MIME_TYPES:
        disposition = _download_disposition(file_obj, force=False)
        url = generate_presigned_url(file_obj.storage_key, response_content_disposition=disposition)
        return PreviewUrlResponse(preview_url=url, mime_type=file_obj.mime_type)

    # `get_max_version_number` == número de versión ACTUAL: `File.storage_key`
    # siempre refleja la última fila de `file_versions` (ver docstring de
    # `FileVersion`), así que el máximo ya usado ES el número vigente -- no
    # hace falta una columna aparte en `File` para esto.
    version_number = file_version_repo.get_max_version_number(db, file_obj.id)
    cache_key = office_preview_key(file_obj.id, version_number)

    if not object_exists_private(cache_key):
        # Fail-fast ANTES de leer nada de MinIO ni de hablarle al conversor --
        # ver el comentario de `MAX_OFFICE_PREVIEW_SOURCE_BYTES` más arriba.
        if file_obj.size_bytes > MAX_OFFICE_PREVIEW_SOURCE_BYTES:
            max_mb = MAX_OFFICE_PREVIEW_SOURCE_BYTES // (1024 * 1024)
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"El archivo supera el tamaño máximo permitido para generar una vista previa ({max_mb} MB)",
            )
        _enforce_office_preview_rate_limit(current_user)

        content = _read_private_object(file_obj.storage_key)
        try:
            pdf_bytes = convert_office_to_pdf(content, file_obj.name)
        except RuntimeError as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
        upload_private_file_at_key(cache_key, pdf_bytes, "application/pdf")

    url = generate_presigned_url(cache_key)
    return PreviewUrlResponse(preview_url=url, mime_type="application/pdf")


@files_router.patch("/{file_id}", response_model=FileOut)
def update_file(
    file_id: UUID,
    payload: FileUpdate,
    db: Session = Depends(get_db),
    # Gate de la dependency bajado a "files.view" (lo tiene el rol USER por
    # defecto) -- "files.rename"/"files.move" se siguen exigiendo
    # EXPLÍCITAMENTE más abajo, campo por campo, cuando "name"/"folder_id"
    # vienen seteados. Mismo criterio y misma razón que update_folder (ver su
    # comentario): favoritear es una preferencia personal ya protegida por
    # ownership (_get_owned_file), no una operación de rename/move.
    current_user: User = Depends(has_permission(["files.view"])),
):
    file_obj = _get_owned_file(db, file_id, current_user, active_only=True)
    fields_set = payload.model_fields_set
    is_admin = _is_admin(current_user)
    user_perms = current_user.permissions or []

    if "name" in fields_set:
        if not (is_admin or "files.rename" in user_perms):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tiene permiso para renombrar archivos")
        if payload.name is not None:
            file_obj.name = payload.name

    if "folder_id" in fields_set:
        if not (is_admin or "files.move" in user_perms):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tiene permiso para mover archivos")
        new_folder_id = payload.folder_id
        if new_folder_id is not None:
            _get_target_parent_folder(db, new_folder_id, file_obj.owner_id)
        file_obj.folder_id = new_folder_id

    if "is_favorite" in fields_set and payload.is_favorite is not None:
        file_obj.is_favorite = payload.is_favorite

    db.commit()
    db.refresh(file_obj)
    return file_obj


@files_router.put("/{file_id}/tags", response_model=FileOut)
def set_file_tags(
    file_id: UUID,
    payload: TagIdsUpdate,
    db: Session = Depends(get_db),
    # Mismo gate que update_file (files.view, no files.rename/move) -- ver
    # comentario de set_folder_tags / update_file más arriba.
    current_user: User = Depends(has_permission(["files.view"])),
):
    """Reemplaza el set COMPLETO de etiquetas del archivo (no incremental).
    Todos los `tag_ids` deben pertenecer al usuario dueño del archivo --
    ver `_resolve_owned_tags`."""
    file_obj = _get_owned_file(db, file_id, current_user, active_only=True)
    file_obj.tags = _resolve_owned_tags(db, file_obj.owner_id, payload.tag_ids)
    db.commit()
    db.refresh(file_obj)
    return file_obj


@files_router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    file_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.delete"])),
):
    file_obj = _get_owned_file(db, file_id, current_user, active_only=True)
    file_obj.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return None


@files_router.post("/{file_id}/restore", response_model=FileOut)
def restore_file(
    file_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.delete"])),
):
    file_obj = _get_owned_file(db, file_id, current_user, active_only=False)
    if file_obj.deleted_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo no está en la papelera")
    if file_obj.folder_id is not None:
        # Si la carpeta contenedora sigue en la papelera (o ya no existe),
        # desanclar a la raíz en vez de dejarlo restaurado pero invisible
        # colgado de un padre borrado.
        parent = folder_repo.get(db, file_obj.folder_id)
        if not parent or parent.deleted_at is not None:
            file_obj.folder_id = None
    file_obj.deleted_at = None
    db.commit()
    db.refresh(file_obj)
    return file_obj


@files_router.post("/{file_id}/copy", response_model=FileOut, status_code=status.HTTP_201_CREATED)
def copy_file(
    file_id: UUID,
    payload: Optional[CopyRequest] = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.upload"])),
):
    """Copia un archivo propio a la misma carpeta (nombre con sufijo
    " (copia)") o a otra carpeta del mismo dueño (mismo nombre). Requiere
    `files.upload` -- copiar consume cuota real, ni más ni menos que subir un
    archivo nuevo idéntico.

    Ownership del origen validado por `_get_owned_file`, MISMO patrón que
    `download_file`/`delete_file` -- nunca se copia un archivo ajeno solo
    porque el caller conoce/adivina su ID (ver test_files_copy.py, caso IDOR)."""
    source = _get_owned_file(db, file_id, current_user, active_only=True)

    dest_folder_id = _resolve_copy_destination(db, source.owner_id, source.folder_id, payload)
    same_location = dest_folder_id == source.folder_id
    new_name = _copy_with_suffix(source.name, same_location=same_location)

    reservations: List[tuple] = []
    uploaded_keys: List[str] = []
    created_ids: List[UUID] = []
    try:
        new_file = _copy_file_object(
            db,
            source,
            owner_id=source.owner_id,
            folder_id=dest_folder_id,
            name=new_name,
            reservations=reservations,
            uploaded_keys=uploaded_keys,
            created_ids=created_ids,
        )
        db.commit()
    except Exception:
        _rollback_copy(db, reservations, uploaded_keys)
        raise
    db.refresh(new_file)
    # La copia se re-indexa (contenido/OCR), igual que una subida.
    _enqueue_content_indexing(new_file.id)
    return new_file


# ============================================================
# VERSIONES -- historial de versiones de un archivo (Ronda 4)
# ============================================================

async def _create_new_file_version(
    db: Session,
    file_obj: FileModel,
    *,
    content: bytes,
    original_filename: Optional[str],
    declared_content_type: Optional[str],
    created_by_id: UUID,
    quota_owner_id: UUID,
) -> FileModel:
    """Crea una versión NUEVA de `file_obj`: sube el contenido a MinIO con
    una `storage_key` NUEVA (nunca pisa la vieja -- el blob anterior se
    conserva como historial real), reserva cuota por el tamaño COMPLETO del
    contenido nuevo contra `quota_owner_id`, crea la fila `FileVersion`
    (`version_number = max + 1`) y actualiza
    `File.storage_key/size_bytes/mime_type` a los datos de la versión nueva
    (`updated_at` se actualiza solo, vía `onupdate=func.now()`).

    A diferencia del reemplazo de contenido de Ronda 3 (que liberaba el
    tamaño viejo antes de reservar el nuevo), acá NO se libera nada -- cada
    versión ocupa espacio real adicional en MinIO porque el blob anterior
    sigue existiendo como historial, así que la cuota tiene que reflejar la
    suma de todas las versiones, no solo la última. Igual que en
    `_validate_and_store_upload`, la reserva de cuota es ANTES de subir a
    MinIO (si falla la reserva, no se sube nada) y se revierte si la subida
    falla después.

    Reusado por `POST /files/{id}/versions` (subida directa, `created_by_id`
    = el propio dueño) y `PUT /shares/{share_id}/content` (reemplazo vía
    share de Ronda 3, `created_by_id` = el destinatario que subió el
    reemplazo) -- MISMO comportamiento de versionado y cuota en los dos
    casos, ver reporte de Ronda 4."""
    _, extension = os.path.splitext(original_filename or file_obj.name)
    declared_content_type = declared_content_type or "application/octet-stream"
    content_type = _resolve_verified_content_type(content, declared_content_type)

    # Ronda 7: escaneo de malware (ClamAV) -- ANTES de reservar cuota y de
    # subir nada a MinIO. Ver `_scan_for_malware_or_raise` para la política
    # fail-closed completa (y por qué esta función pasó a ser `async` --
    # el escaneo corre en threadpool, nunca bloqueante en el loop).
    await _scan_for_malware_or_raise(content, original_name=original_filename or file_obj.name)

    reserve_upload_bytes(db, quota_owner_id, len(content))

    try:
        new_storage_key = upload_private_file(
            path=f"files/{file_obj.owner_id}",
            content=content,
            extension=extension,
            content_type=content_type,
        )
    except Exception:
        release_upload_bytes(db, quota_owner_id, len(content))
        raise

    next_version_number = file_version_repo.get_max_version_number(db, file_obj.id) + 1
    db.add(
        FileVersion(
            file_id=file_obj.id,
            version_number=next_version_number,
            storage_key=new_storage_key,
            size_bytes=len(content),
            mime_type=content_type,
            created_by_id=created_by_id,
        )
    )

    file_obj.storage_key = new_storage_key
    file_obj.size_bytes = len(content)
    file_obj.mime_type = content_type
    db.commit()
    db.refresh(file_obj)
    # Ronda 6: el contenido cambió (versión nueva) -- re-encolar indexación,
    # reemplaza cualquier extracción vieja (ver `file_content_index_repo.upsert`).
    _enqueue_content_indexing(file_obj.id)
    return file_obj


def _file_version_to_out(version: FileVersion) -> FileVersionOut:
    """Enriquece una `FileVersion` con el email/nombre de quien la subió,
    resolviendo la relación `FileVersion.created_by` (mismo criterio de no
    guardar el email en el propio modelo que ya usa `_share_to_out` para
    `shared_by_email`, ver su docstring)."""
    created_by_email = None
    created_by_name = None
    if version.created_by is not None:
        created_by_email = version.created_by.email
        created_by_name = f"{version.created_by.first_name} {version.created_by.last_name or ''}".strip() or None

    return FileVersionOut(
        id=version.id,
        file_id=version.file_id,
        version_number=version.version_number,
        size_bytes=version.size_bytes,
        mime_type=version.mime_type,
        created_at=version.created_at,
        created_by_id=version.created_by_id,
        created_by_email=created_by_email,
        created_by_name=created_by_name,
    )


@files_router.post("/{file_id}/versions", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def upload_file_version(
    file_id: UUID,
    file: UploadFile = UploadFileParam(...),
    db: Session = Depends(get_db),
    # Mismo permiso base que subir un archivo nuevo (`upload_file`) --
    # subir una versión nueva es, en los hechos, subir contenido nuevo.
    # Ownership del archivo lo valida `_get_owned_file` más abajo.
    current_user: User = Depends(has_permission(["files.upload"])),
):
    """Sube una versión NUEVA del contenido de `file_id` -- no reemplaza el
    blob viejo (se conserva como historial, ver `_create_new_file_version`),
    reserva cuota real por el tamaño completo del contenido nuevo contra el
    dueño del archivo. Devuelve el `File` ya actualizado a la versión
    nueva (mismo shape que `upload_file`/`replace_file_via_share`)."""
    file_obj = _get_owned_file(db, file_id, current_user, active_only=True)

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"El archivo supera el tamaño máximo permitido ({settings.MAX_UPLOAD_SIZE_MB} MB)",
        )

    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"El archivo supera el tamaño máximo permitido ({settings.MAX_UPLOAD_SIZE_MB} MB)",
        )

    return await _create_new_file_version(
        db,
        file_obj,
        content=content,
        original_filename=file.filename,
        declared_content_type=file.content_type,
        created_by_id=current_user.id,
        quota_owner_id=file_obj.owner_id,
    )


@files_router.get("/{file_id}/versions", response_model=List[FileVersionOut])
def list_file_versions(
    file_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.view"])),
):
    """Historial completo de versiones de `file_id`, más reciente primero.
    Ownership del archivo requerido (`_get_owned_file`) -- mismo criterio
    anti-IDOR que el resto del módulo."""
    file_obj = _get_owned_file(db, file_id, current_user, active_only=True)
    versions = file_version_repo.get_for_file(db, file_obj.id)
    return [_file_version_to_out(v) for v in versions]


@files_router.get("/{file_id}/index-status", response_model=FileIndexStatusOut)
def get_file_index_status(
    file_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.view"])),
):
    """Estado de la extracción de texto/OCR de `file_id` (Ronda 6) -- para
    que el frontend pueda mostrar "todavía no indexado" mientras la tarea
    async corre. Sin fila en `file_content_index` todavía (tarea recién
    encolada, o nunca se disparó) se responde 'pending' igual que si la fila
    existiera con ese status -- ver docstring de `FileIndexStatusOut`."""
    file_obj = _get_owned_file(db, file_id, current_user, active_only=True)
    record = file_content_index_repo.get_by_file_id(db, file_obj.id)
    if record is None:
        return FileIndexStatusOut(status="pending", indexed_at=None)
    return FileIndexStatusOut(status=record.extraction_status, indexed_at=record.indexed_at)


@files_router.post("/{file_id}/versions/{version_id}/restore", response_model=FileOut)
def restore_file_version(
    file_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.upload"])),
):
    """Restaura `version_id` como el contenido actual de `file_id`. NO sube
    nada nuevo a MinIO -- el blob de esa versión vieja ya existe, se le
    apunta `File.storage_key/size_bytes/mime_type` directo. Se crea una
    `FileVersion` NUEVA (`version_number = max + 1`) que apunta al MISMO
    `storage_key` de la versión restaurada, para que el historial muestre
    "se restauró la vN" como un evento nuevo sin duplicar el blob -- esto NO
    consume cuota adicional (no hay bytes nuevos, ya estaban contados).

    `version_id` tiene que pertenecer REALMENTE a `file_id` -- 404 si no
    (`file_version_repo.get_by_id_for_file`, mismo criterio anti-IDOR que el
    resto del módulo: nunca confiar en que el cliente mande un `version_id`
    de un archivo ajeno solo porque adivinó el UUID)."""
    file_obj = _get_owned_file(db, file_id, current_user, active_only=True)

    version = file_version_repo.get_by_id_for_file(db, version_id, file_obj.id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Versión no encontrada")

    next_version_number = file_version_repo.get_max_version_number(db, file_obj.id) + 1
    db.add(
        FileVersion(
            file_id=file_obj.id,
            version_number=next_version_number,
            storage_key=version.storage_key,
            size_bytes=version.size_bytes,
            mime_type=version.mime_type,
            created_by_id=current_user.id,
        )
    )

    file_obj.storage_key = version.storage_key
    file_obj.size_bytes = version.size_bytes
    file_obj.mime_type = version.mime_type
    db.commit()
    db.refresh(file_obj)
    # Ronda 6: el contenido "actual" cambió (aunque el blob ya existía) --
    # re-encolar indexación por el mismo criterio que una versión nueva.
    _enqueue_content_indexing(file_obj.id)
    return file_obj


# ============================================================
# SHARES -- compartir por link (Hito 2), rutas autenticadas
# ============================================================

@files_router.post("/{file_id}/shares", response_model=ShareOut, status_code=status.HTTP_201_CREATED)
def create_file_share(
    file_id: UUID,
    payload: ShareCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["shares.create"])),
):
    file_obj = _get_owned_file(db, file_id, current_user, active_only=True)
    share = _create_share(
        db,
        file_id=file_obj.id,
        folder_id=None,
        resource_name=file_obj.name,
        current_user=current_user,
        payload=payload,
    )
    return _share_to_out(share)


@files_router.get("/{file_id}/shares", response_model=List[ShareOut])
def list_file_shares(
    file_id: UUID,
    db: Session = Depends(get_db),
    # Cualquiera de los tres alcanza para VER los shares de un recurso propio
    # -- MANAGER tiene create/revoke pero no manage (permisos reales, ver
    # app/core/permissions.py), y sin esto no podía ver el link que acababa
    # de crear ni el estado tras revocarlo (hallazgo bloqueante de la ronda de
    # feedback de Hito 2, 2026-09-06). El ownership real lo sigue validando
    # _get_owned_file, esto solo amplía quién pasa el gate de permiso inicial.
    current_user: User = Depends(has_permission(["shares.create", "shares.revoke", "shares.manage"])),
):
    file_obj = _get_owned_file(db, file_id, current_user, active_only=False)
    shares = share_repo.get_for_file(db, file_obj.id)
    return [_share_to_out(s) for s in shares]


@folders_router.post("/{folder_id}/shares", response_model=ShareOut, status_code=status.HTTP_201_CREATED)
def create_folder_share(
    folder_id: UUID,
    payload: ShareCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["shares.create"])),
):
    folder = _get_owned_folder(db, folder_id, current_user, active_only=True)
    share = _create_share(
        db,
        file_id=None,
        folder_id=folder.id,
        resource_name=folder.name,
        current_user=current_user,
        payload=payload,
    )
    return _share_to_out(share)


@folders_router.get("/{folder_id}/shares", response_model=List[ShareOut])
def list_folder_shares(
    folder_id: UUID,
    db: Session = Depends(get_db),
    # Mismo criterio que list_file_shares -- ver comentario ahí.
    current_user: User = Depends(has_permission(["shares.create", "shares.revoke", "shares.manage"])),
):
    folder = _get_owned_folder(db, folder_id, current_user, active_only=False)
    shares = share_repo.get_for_folder(db, folder.id)
    return [_share_to_out(s) for s in shares]


@shares_router.delete("/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(
    share_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["shares.revoke"])),
):
    """Revoca un share (`revoked_at = now()`, no se borra la fila -- se
    conserva como historial). Valida que el share pertenezca a un recurso
    del usuario actual (o admin) reusando los mismos helpers de ownership
    que el resto del módulo -- 404 si el archivo/carpeta no es suyo, mismo
    criterio "no filtrar" que el resto de este router."""
    share = share_repo.get(db, share_id)
    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")

    if share.file_id is not None:
        _get_owned_file(db, share.file_id, current_user, active_only=False)
    else:
        _get_owned_folder(db, share.folder_id, current_user, active_only=False)

    if share.revoked_at is None:
        share.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return None


# ============================================================
# SHARES DIRIGIDOS A UN USUARIO -- rutas autenticadas (Ronda 3)
# ============================================================
# A diferencia del link público (por token, sin auth), un share con
# `shared_with_user_id` seteado se accede SIEMPRE autenticado, por su propio
# `id` -- nunca por /public/shares. Registrar "/with-me" ANTES de "/{share_id}"
# en este mismo router es obligatorio: FastAPI prueba las rutas en el orden
# en que se agregan, y "with-me" no es un UUID válido -- si "/{share_id}"
# quedara primero, "with-me" caería ahí y devolvería 422 en vez de la lista.

@shares_router.get("/with-me", response_model=List[ShareOut])
def list_shares_with_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Shares dirigidos a mí. Sin gate de permiso RBAC (a diferencia de
    `list_file_shares`/`list_folder_shares`, que exigen shares.create/revoke/
    manage sobre un recurso PROPIO) -- esto es la bandeja de entrada de lo
    que otros me compartieron, no una gestión sobre mis propios recursos.

    `with_resource_info=True` -- a diferencia de crear/listar-por-recurso,
    esta pantalla necesita mostrar QUÉ le compartieron y QUIÉN se lo
    compartió, no solo IDs (ver docstring de `_share_to_out`; hallazgo del
    agente de frontend, Ronda 3: sin esto la UI solo podía mostrar UUIDs
    pelados)."""
    shares = share_repo.get_for_recipient(db, current_user.id)
    return [_share_to_out(s, with_resource_info=True) for s in shares]


def _build_share_content_response(
    db: Session,
    share: Share,
    *,
    path: Optional[UUID],
    force_download: bool,
):
    """Arma la respuesta de contenido de un share (archivo o carpeta) --
    misma lógica para el endpoint público (`get_public_share`, por token) y
    el autenticado (`get_share_content`, por id), extraída para no duplicar
    el chequeo anti-IDOR de `path` contra el subárbol real del share."""
    if share.file_id is not None:
        file_obj = file_repo.get_active(db, share.file_id)
        if not file_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")
        disposition = _download_disposition(file_obj, force=force_download)
        url = generate_presigned_url(file_obj.storage_key, response_content_disposition=disposition)
        return PublicFileShareOut(
            name=file_obj.name,
            size_bytes=file_obj.size_bytes,
            mime_type=file_obj.mime_type,
            download_url=url,
        )

    root_folder = folder_repo.get_active(db, share.folder_id)
    if not root_folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")

    if path is None or path == root_folder.id:
        target_folder = root_folder
    else:
        # `path` tiene que ser un descendiente REAL de la carpeta compartida --
        # nunca confiar en que el cliente mande un folder_id legítimo, un
        # atacante puede mandar cualquier UUID de carpeta ajena tratando de
        # usar este share como llave maestra.
        descendant_ids = set(folder_repo.get_descendant_ids(db, root_folder.id))
        if path not in descendant_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")
        target_folder = folder_repo.get_active(db, path)
        if not target_folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")

    folders = folder_repo.get_children(db, root_folder.owner_id, target_folder.id)
    files = file_repo.get_children(db, root_folder.owner_id, target_folder.id)
    return PublicFolderShareOut(
        name=target_folder.name,
        folder_id=target_folder.id,
        folders=folders,
        files=files,
    )


def _resolve_share_download_target(db: Session, share: Share, file_id: UUID) -> FileModel:
    """Resuelve y valida el `File` a descargar dentro de un share -- MISMO
    chequeo anti-IDOR para el endpoint público y el autenticado (extraído de
    `download_public_share_file`, ver docstring de `_build_share_content_response`
    para el motivo de la extracción)."""
    if share.file_id is not None:
        if file_id != share.file_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")
        file_obj = file_repo.get_active(db, file_id)
        if not file_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")
        return file_obj

    file_obj = file_repo.get_active(db, file_id)
    if not file_obj or file_obj.folder_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")
    # El archivo tiene que pertenecer al subárbol de la carpeta compartida
    # (la carpeta misma o un descendiente real) -- mismo chequeo anti-IDOR
    # que en _build_share_content_response, ahora sobre archivos en vez de
    # carpetas.
    allowed_folder_ids = {share.folder_id} | set(folder_repo.get_descendant_ids(db, share.folder_id))
    if file_obj.folder_id not in allowed_folder_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")
    return file_obj


# Throttle por USUARIO autenticado de los endpoints de shares dirigidos
# (mismo patrón que `_enforce_office_preview_rate_limit`): lecturas 60/min,
# escrituras (subida/reemplazo, que además leen el archivo completo a
# memoria) 30/min (la UI sube de a un archivo, >10 seguidos es legítimo).
# Ventana FIJA (RateLimiter.check_fixed_window): N por ventana de 60s, no "N
# sin pausa de 60s".
DIRECTED_SHARE_READ_RATE_LIMIT_MAX = 60
DIRECTED_SHARE_WRITE_RATE_LIMIT_MAX = 30
DIRECTED_SHARE_RATE_LIMIT_WINDOW_SECONDS = 60


def _enforce_directed_share_rate_limit(current_user: User, bucket: str) -> None:
    """`bucket` es 'read' o 'write'. Clave por usuario: `directed_share_read:{id}`
    / `directed_share_write:{id}`."""
    max_attempts = (
        DIRECTED_SHARE_WRITE_RATE_LIMIT_MAX if bucket == "write" else DIRECTED_SHARE_READ_RATE_LIMIT_MAX
    )
    rl_key = f"directed_share_{bucket}:{current_user.id}"
    is_allowed, rl_message = RateLimiter.check_fixed_window(
        rl_key, max_requests=max_attempts, window_seconds=DIRECTED_SHARE_RATE_LIMIT_WINDOW_SECONDS
    )
    if not is_allowed:
        raise too_many_requests(rl_message)


def _get_directed_share_for_viewer(db: Session, share_id: UUID, current_user: User) -> Share:
    """Share DIRIGIDO (shared_with_user_id NOT NULL) vigente, accesible por
    el destinatario o por el dueño del recurso (`created_by_id`) -- 404 para
    cualquier otro caso (share inexistente, público, revocado, expirado, o
    de un tercero), mismo criterio "no filtrar por qué" que el resto del
    módulo. Un share revocado no debería seguir siendo consultable ni por su
    propio destinatario -- misma vigencia que exige `_get_valid_share` para
    el link público."""
    share = share_repo.get(db, share_id)
    now = datetime.now(timezone.utc)
    if (
        not share
        or share.shared_with_user_id is None
        or share.revoked_at is not None
        or (share.expires_at is not None and share.expires_at <= now)
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")
    if current_user.id not in (share.shared_with_user_id, share.created_by_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")
    return share


@shares_router.get("/{share_id}")
def get_share_content(
    share_id: UUID,
    path: Optional[UUID] = Query(None),
    force_download: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Contenido de un share dirigido -- mismo shape que el endpoint público
    (`get_public_share`), pero autenticado y solo para el destinatario o el
    dueño (ver `_get_directed_share_for_viewer`). Acepta `path` para navegar
    subcarpetas igual que el público, por paridad con esa UI."""
    _enforce_directed_share_rate_limit(current_user, "read")
    share = _get_directed_share_for_viewer(db, share_id, current_user)
    return _build_share_content_response(db, share, path=path, force_download=force_download)


@shares_router.get("/{share_id}/download/{file_id}", response_model=DownloadUrlResponse)
def download_share_file(
    request: Request,
    share_id: UUID,
    file_id: UUID,
    force_download: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _enforce_directed_share_rate_limit(current_user, "read")
    share = _get_directed_share_for_viewer(db, share_id, current_user)
    file_obj = _resolve_share_download_target(db, share, file_id)
    disposition = _download_disposition(file_obj, force=force_download)
    url = generate_presigned_url(file_obj.storage_key, response_content_disposition=disposition)
    _audit_download(
        db, request,
        user_id=current_user.id, user_email=current_user.email,
        file_id=file_obj.id, file_name=file_obj.name, via="directed_share",
        share_id=share.id,
    )
    return DownloadUrlResponse(download_url=url)


def _get_share_for_write(db: Session, share_id: UUID, current_user: User) -> Share:
    """Share vigente donde `current_user` es el destinatario o el dueño del
    recurso -- 404 para cualquier otro (ownership, mismo criterio "no
    filtrar" del resto del módulo). Deliberadamente SEPARADO de la
    validación de `permission='edit'` (`_require_edit_permission`, que debe
    dar 403 -- ver su docstring): esta función no filtra por si el share es
    público o de solo lectura, solo por si el caller tiene algo que ver con
    el share en absoluto."""
    share = share_repo.get(db, share_id)
    now = datetime.now(timezone.utc)
    if (
        not share
        or share.revoked_at is not None
        or (share.expires_at is not None and share.expires_at <= now)
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")
    if current_user.id not in (share.shared_with_user_id, share.created_by_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")
    return share


def _require_edit_permission(share: Share) -> None:
    """403 si el share no permite escribir: un link público
    (shared_with_user_id NULL) es SIEMPRE de solo lectura sin importar
    `permission` -- el campo no aplica a links públicos (nadie anónimo puede
    escribir, ver docstring de `ShareCreate`/`Share`). Un share dirigido con
    `permission='view'` cae en el mismo 403."""
    if share.shared_with_user_id is None or share.permission != "edit":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este enlace no permite subir o modificar contenido",
        )


@shares_router.post("/{share_id}/files", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def upload_file_via_share(
    share_id: UUID,
    file: UploadFile = UploadFileParam(...),
    db: Session = Depends(get_db),
    # files.upload -- lo mismo que exige el upload normal (app/files/router.py
    # ::upload_file). El rol USER por defecto ya lo tiene (uso básico del
    # Drive); el gate real de "puede escribir EN ESTE share puntual" lo hacen
    # `_get_share_for_write`/`_require_edit_permission` más abajo, no esto.
    current_user: User = Depends(has_permission(["files.upload"])),
):
    """El destinatario de un share de CARPETA con `permission='edit'` sube un
    archivo nuevo dentro de ella. La cuota se reserva contra el DUEÑO real de
    la carpeta (`target_folder.owner_id`), nunca contra `current_user` -- ver
    diseño de Ronda 3."""
    _enforce_directed_share_rate_limit(current_user, "write")
    share = _get_share_for_write(db, share_id, current_user)
    _require_edit_permission(share)
    if share.folder_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Este enlace no comparte una carpeta")

    target_folder = folder_repo.get_active(db, share.folder_id)
    if not target_folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"El archivo supera el tamaño máximo permitido ({settings.MAX_UPLOAD_SIZE_MB} MB)",
        )

    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"El archivo supera el tamaño máximo permitido ({settings.MAX_UPLOAD_SIZE_MB} MB)",
        )

    return await _validate_and_store_upload(
        db,
        owner_id=target_folder.owner_id,
        folder_id=target_folder.id,
        upload=file,
        content=content,
        created_by_id=current_user.id,
    )


@shares_router.put("/{share_id}/content", response_model=FileOut)
async def replace_file_via_share(
    share_id: UUID,
    file: UploadFile = UploadFileParam(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.upload"])),
):
    """El destinatario de un share de ARCHIVO con `permission='edit'`
    reemplaza su contenido: mismo `file_id`, versión NUEVA (Ronda 4 -- ver
    `_create_new_file_version`). El nombre del archivo NO se toca -- se
    reemplaza el contenido "in place", no se renombra (decisión de diseño,
    ver reporte final).

    Refactor de Ronda 4: antes este endpoint liberaba la cuota del tamaño
    viejo y borraba su `storage_key` de MinIO al reemplazar (sin dejar
    rastro del contenido anterior). Ahora reusa la MISMA lógica de "crear
    versión nueva" que `POST /files/{id}/versions` -- el blob viejo se
    conserva como historial real (consume cuota real adicional, ya NO se
    libera) y queda una `FileVersion` con `created_by_id` = el destinatario
    que subió el reemplazo (no el dueño), mientras que la cuota se sigue
    reservando contra el DUEÑO real del archivo (mismo criterio de Ronda 3)."""
    _enforce_directed_share_rate_limit(current_user, "write")
    share = _get_share_for_write(db, share_id, current_user)
    _require_edit_permission(share)
    if share.file_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Este enlace no comparte un archivo")

    target_file = file_repo.get_active(db, share.file_id)
    if not target_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"El archivo supera el tamaño máximo permitido ({settings.MAX_UPLOAD_SIZE_MB} MB)",
        )

    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"El archivo supera el tamaño máximo permitido ({settings.MAX_UPLOAD_SIZE_MB} MB)",
        )

    return await _create_new_file_version(
        db,
        target_file,
        content=content,
        original_filename=file.filename or target_file.name,
        declared_content_type=file.content_type,
        created_by_id=current_user.id,
        quota_owner_id=target_file.owner_id,
    )


# ============================================================
# SHARES PÚBLICOS -- sin autenticación (prefix /public/shares)
# ============================================================

# Cada request a un share de carpeta dispara una query recursiva
# (WITH RECURSIVE, get_descendant_ids) -- sin límite es superficie de DoS
# barata para quien no tiene el token siquiera (hallazgo medio de la ronda de
# feedback de Hito 2, 2026-09-06). No es fuerza bruta de credenciales (el
# token tiene 256 bits de entropía), es solo throttle de volumen -- un límite
# fijo alcanza, no hace falta que sea configurable ni tan estricto como login.
PUBLIC_SHARE_RATE_LIMIT_MAX_REQUESTS = 30
PUBLIC_SHARE_RATE_LIMIT_WINDOW_SECONDS = 60


def _enforce_public_share_rate_limit(request: Request) -> None:
    """Throttle por IP de los endpoints públicos de shares, reusando la misma
    infraestructura de Redis que ya usa `/auth/login` (`RateLimiter`, ver
    app/auth/service.py)."""
    # IP real (respeta TRUSTED_PROXY_IPS): tras nginx, request.client.host
    # es la IP del proxy y todos los visitantes compartirían un solo cupo.
    ip_address = get_real_ip(request)
    # IPv6 agrupada por /64 (rate_limit_ip_key); IPv4 sin cambio.
    rl_key = f"public_share:{rate_limit_ip_key(ip_address)}"
    is_allowed, rl_message = RateLimiter.check_fixed_window(
        rl_key,
        max_requests=PUBLIC_SHARE_RATE_LIMIT_MAX_REQUESTS,
        window_seconds=PUBLIC_SHARE_RATE_LIMIT_WINDOW_SECONDS,
    )
    if not is_allowed:
        raise too_many_requests(rl_message)


def _get_valid_share(db: Session, token: str) -> Share:
    """Busca un share por token y valida que esté vigente (no revocado, no
    expirado). 404 genérico en cualquier caso de invalidez -- mismo criterio
    "no filtrar por qué" que el resto de los endpoints públicos de este
    router, para no ayudar a un atacante a distinguir "token no existe" de
    "token revocado" de "token expirado"."""
    share = share_repo.get_by_token(db, token)
    now = datetime.now(timezone.utc)
    if (
        not share
        or share.revoked_at is not None
        or (share.expires_at is not None and share.expires_at <= now)
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")
    return share


def _verify_share_password(share: Share, provided_password: Optional[str]) -> None:
    """Si el link público tiene `password_hash` (Ronda 3), exige que
    `provided_password` la matchee -- 401 tanto si falta como si es
    incorrecta (mismo mensaje en los dos casos, no distingue cuál para no
    darle a un atacante una señal de "casi" que ayude a fuerza bruta).

    La contraseña viaja por el header `X-Share-Password` (NO por query
    param): un query param queda en logs de acceso del servidor/proxy, en el
    historial del navegador y en el header `Referer` de cualquier request
    saliente desde esa página -- un header custom no viaja a ninguno de los
    tres. Elegido sobre el query param a propósito por ese motivo (AppSec),
    documentado acá para que sea el único lugar donde hace falta consultarlo:
    el frontend tiene que mandar este mismo header en AMBOS endpoints
    públicos (`GET /public/shares/{token}` y `.../download/{file_id}`)."""
    if share.password_hash is None:
        return
    if not provided_password or not verify_password(provided_password, share.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Contraseña requerida o incorrecta")


@public_shares_router.get("/{token}")
def get_public_share(
    request: Request,
    token: str,
    path: Optional[UUID] = Query(None),
    force_download: bool = Query(False),
    x_share_password: Optional[str] = Header(None, alias="X-Share-Password"),
    db: Session = Depends(get_db),
):
    _enforce_public_share_rate_limit(request)
    share = _get_valid_share(db, token)
    _verify_share_password(share, x_share_password)
    return _build_share_content_response(db, share, path=path, force_download=force_download)


@public_shares_router.get("/{token}/download/{file_id}", response_model=PublicDownloadResponse)
def download_public_share_file(
    request: Request,
    token: str,
    file_id: UUID,
    force_download: bool = Query(False),
    x_share_password: Optional[str] = Header(None, alias="X-Share-Password"),
    db: Session = Depends(get_db),
):
    _enforce_public_share_rate_limit(request)
    share = _get_valid_share(db, token)
    _verify_share_password(share, x_share_password)
    file_obj = _resolve_share_download_target(db, share, file_id)
    disposition = _download_disposition(file_obj, force=force_download)
    url = generate_presigned_url(file_obj.storage_key, response_content_disposition=disposition)
    _audit_download(
        db, request,
        user_id=None, user_email=None,
        file_id=file_obj.id, file_name=file_obj.name, via="public_share",
        share_id=share.id,
    )
    return PublicDownloadResponse(download_url=url)
