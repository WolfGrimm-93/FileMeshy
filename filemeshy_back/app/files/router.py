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
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.access_control.service import has_permission
from app.auth.service import RateLimiter
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.files.models import File as FileModel, Folder, Share
from app.files.repository import file_repo, folder_repo, share_repo
from app.files.schemas import (
    BreadcrumbItem,
    CopyRequest,
    DirectoryListing,
    DownloadUrlResponse,
    FileOut,
    FileUpdate,
    FolderCreate,
    FolderDetail,
    FolderOut,
    FolderUpdate,
    PublicDownloadResponse,
    PublicFileShareOut,
    PublicFolderShareOut,
    ShareCreate,
    ShareOut,
    TagIdsUpdate,
)
from app.files.service import (
    delete_private_file,
    detect_image_type,
    generate_presigned_url,
    is_pdf_content,
    upload_private_file,
)
from app.storage_quota.service import reserve_upload_bytes, release_upload_bytes
from app.tags.models import Tag
from app.tags.repository import tag_repo
from app.users.models import User

folders_router = APIRouter()
files_router = APIRouter()
shares_router = APIRouter()
public_shares_router = APIRouter()

# Tipos MIME verificados por contenido real (magic bytes, ver upload_file) que
# se sirven SIN forzar `attachment` -- permiten preview inline (imagen en
# <img>, PDF en <iframe>). Cualquier otro tipo, SVG incluido a propósito
# (es XML, puede llevar <script> embebido y ejecuta igual que HTML), sigue
# forzando `attachment` como todo el resto de Hito 1.
INLINE_SAFE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
}

_VERIFIED_IMAGE_MIME_BY_FORMAT = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}

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


def _share_to_out(share: Share) -> ShareOut:
    """`is_active` no es una columna real -- se calcula acá, un solo lugar,
    para que las dos rutas que devuelven ShareOut (crear y listar) usen
    siempre el mismo criterio."""
    now = datetime.now(timezone.utc)
    is_active = share.revoked_at is None and (share.expires_at is None or share.expires_at > now)
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
    )


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
) -> FileModel:
    """Copia un único archivo (bytes + fila nueva), reservando cuota real
    igual que `upload_file`. No hace `commit` -- lo hace el caller una vez
    que terminó (todo el archivo, o todo el subárbol de una carpeta)."""
    content = _read_private_object(source_file.storage_key)
    size = len(content)

    _reserve_copy_quota(owner_id, size)
    reservations.append((owner_id, size))

    try:
        storage_key = upload_private_file(
            path=f"files/{owner_id}",
            content=content,
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
    )
    db.add(new_file)
    db.flush()
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
    try:
        new_folder = _copy_folder_tree(
            db,
            source_folder,
            owner_id=source_folder.owner_id,
            parent_id=dest_parent_id,
            name=new_name,
            reservations=reservations,
            uploaded_keys=uploaded_keys,
        )
        db.commit()
    except Exception:
        _rollback_copy(db, reservations, uploaded_keys)
        raise
    db.refresh(new_folder)
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
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
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
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El archivo supera el tamaño máximo permitido ({settings.MAX_UPLOAD_SIZE_MB} MB)",
        )

    original_name = file.filename or "archivo"
    if len(original_name) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre no puede superar los 255 caracteres",
        )
    _, extension = os.path.splitext(original_name)
    content_type = file.content_type or "application/octet-stream"

    # Verificación de tipo real por contenido (magic bytes), NUNCA confiar en
    # el Content-Type que declara el cliente para decidir si un archivo se
    # puede servir inline más adelante (ver _download_disposition) -- lo
    # declarado es texto libre controlado por el atacante. Si el contenido
    # real es una imagen (nunca SVG: es XML, puede llevar <script> embebido
    # y ejecuta igual que HTML) o un PDF real, se sobreescribe `content_type`
    # con el verificado.
    detected_format = detect_image_type(content)
    if detected_format in _VERIFIED_IMAGE_MIME_BY_FORMAT:
        content_type = _VERIFIED_IMAGE_MIME_BY_FORMAT[detected_format]
    elif is_pdf_content(content):
        content_type = "application/pdf"
    elif content_type in INLINE_SAFE_MIME_TYPES:
        # El cliente declaró uno de los tipos "seguros para inline" pero el
        # contenido real no lo confirma -- degradar a un tipo genérico para
        # que _download_disposition nunca lo sirva inline solo por el nombre
        # del Content-Type declarado (ese exacto vector permitía subir un
        # script disfrazado de imagen, hallazgo crítico de la ronda de
        # feedback de Hito 2, 2026-09-06).
        content_type = "application/octet-stream"

    # Cuota de almacenamiento del usuario: chequeo y reserva son la MISMA
    # operación atómica (UPDATE con guard, ver
    # app/storage_quota/service.py::reserve_upload_bytes), ANTES de subir a
    # MinIO -- separar "chequear" de "sumar" en dos pasos dejaba una ventana
    # donde dos uploads concurrentes del mismo usuario, cada uno por debajo
    # del remanente, pasaban el chequeo por separado y sumados superaban el
    # límite (hallazgo de la revisión adversarial, Fase 3, 2026-09-08).
    reserve_upload_bytes(db, current_user.id, len(content))

    try:
        storage_key = upload_private_file(
            path=f"files/{current_user.id}",
            content=content,
            extension=extension,
            content_type=content_type,
        )
    except Exception:
        # La reserva de arriba ya sumó a bytes_used -- si la subida a MinIO
        # falla, hay que liberarla o el contador queda inflado por un
        # archivo que nunca llegó a existir.
        release_upload_bytes(db, current_user.id, len(content))
        raise

    db_file = FileModel(
        name=original_name,
        folder_id=folder_id,
        owner_id=current_user.id,
        storage_key=storage_key,
        size_bytes=len(content),
        mime_type=content_type,
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    return db_file


@files_router.get("/{file_id}", response_model=FileOut)
def get_file(
    file_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.view"])),
):
    return _get_owned_file(db, file_id, current_user, active_only=True)


@files_router.get("/{file_id}/download", response_model=DownloadUrlResponse)
def download_file(
    file_id: UUID,
    force_download: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["files.download"])),
):
    file_obj = _get_owned_file(db, file_id, current_user, active_only=True)
    disposition = _download_disposition(file_obj, force=force_download)
    url = generate_presigned_url(file_obj.storage_key, response_content_disposition=disposition)
    return DownloadUrlResponse(download_url=url)


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
    try:
        new_file = _copy_file_object(
            db,
            source,
            owner_id=source.owner_id,
            folder_id=dest_folder_id,
            name=new_name,
            reservations=reservations,
            uploaded_keys=uploaded_keys,
        )
        db.commit()
    except Exception:
        _rollback_copy(db, reservations, uploaded_keys)
        raise
    db.refresh(new_file)
    return new_file


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
    share = Share(
        file_id=file_obj.id,
        token=secrets.token_urlsafe(32),
        created_by_id=current_user.id,
        expires_at=payload.expires_at,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
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
    share = Share(
        folder_id=folder.id,
        token=secrets.token_urlsafe(32),
        created_by_id=current_user.id,
        expires_at=payload.expires_at,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
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
    ip_address = request.client.host if request.client else "unknown"
    rl_key = f"public_share:{ip_address}"
    is_allowed, rl_message = RateLimiter.check_rate_limit(
        rl_key,
        max_attempts=PUBLIC_SHARE_RATE_LIMIT_MAX_REQUESTS,
        lock_duration=PUBLIC_SHARE_RATE_LIMIT_WINDOW_SECONDS,
    )
    if not is_allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=rl_message)
    RateLimiter.record_attempt(rl_key, window_seconds=PUBLIC_SHARE_RATE_LIMIT_WINDOW_SECONDS)


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


@public_shares_router.get("/{token}")
def get_public_share(
    request: Request,
    token: str,
    path: Optional[UUID] = Query(None),
    force_download: bool = Query(False),
    db: Session = Depends(get_db),
):
    _enforce_public_share_rate_limit(request)
    share = _get_valid_share(db, token)

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


@public_shares_router.get("/{token}/download/{file_id}", response_model=PublicDownloadResponse)
def download_public_share_file(
    request: Request,
    token: str,
    file_id: UUID,
    force_download: bool = Query(False),
    db: Session = Depends(get_db),
):
    _enforce_public_share_rate_limit(request)
    share = _get_valid_share(db, token)

    if share.file_id is not None:
        if file_id != share.file_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")
        file_obj = file_repo.get_active(db, file_id)
        if not file_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")
    else:
        file_obj = file_repo.get_active(db, file_id)
        if not file_obj or file_obj.folder_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")
        # El archivo tiene que pertenecer al subárbol de la carpeta compartida
        # (la carpeta misma o un descendiente real) -- mismo chequeo anti-IDOR
        # que en get_public_share, ahora sobre archivos en vez de carpetas.
        allowed_folder_ids = {share.folder_id} | set(folder_repo.get_descendant_ids(db, share.folder_id))
        if file_obj.folder_id not in allowed_folder_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado")

    disposition = _download_disposition(file_obj, force=force_download)
    url = generate_presigned_url(file_obj.storage_key, response_content_disposition=disposition)
    return PublicDownloadResponse(download_url=url)
