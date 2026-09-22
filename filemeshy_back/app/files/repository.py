"""CRUD de Carpetas y Archivos.

Router-heavy por convención del proyecto (ver notifications/access_control):
esta capa solo hace queries, la lógica de negocio (permisos duales,
detección de ciclos, recursión de papelera) vive en router.py.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session, selectinload

from app.files.models import File, FileContentIndex, FileVersion, Folder, Share
from app.shared.repository_base import CRUDBase
from app.tags.models import file_tags, folder_tags

# Whitelist de columnas ordenables por modelo -- el valor de `sort_by` llega
# directo de un query param del cliente, NUNCA se interpola en el `order_by`
# sin pasar por acá (riesgo de SQL injection vía nombre de columna si se
# usara `getattr`/texto crudo sin validar contra un set cerrado). Cualquier
# valor de `sort_by` fuera de estas claves cae a "name" en vez de tirar error
# (ver `_resolve_sort_column`).
_FOLDER_SORT_COLUMNS = {
    "name": Folder.name,
    "created_at": Folder.created_at,
    "updated_at": Folder.updated_at,
}

_FILE_SORT_COLUMNS = {
    "name": File.name,
    "created_at": File.created_at,
    "updated_at": File.updated_at,
    "size_bytes": File.size_bytes,
}

# Ronda 9 -- único valor de `File.scan_status` que hace a un archivo visible
# en cualquier lectura normal (ver `CRUDFile`, docstring de la clase). Un
# valor 'infected' NUNCA vuelve a 'clean' automáticamente -- solo existe el
# camino manual de moderación (fuera de alcance de esta ronda), así que un
# archivo infectado queda invisible para siempre, que es el comportamiento
# deseado.
_VISIBLE_SCAN_STATUS = "clean"


def _resolve_sort_column(columns: dict, sort_by: str, sort_dir: str):
    """Resuelve `sort_by`/`sort_dir` a una expresión `order_by` real contra la
    whitelist de `columns`. `sort_by` desconocido cae a "name" (sin tirar
    error -- un valor inesperado del cliente no debería romper el listado).
    Cualquier `sort_dir` distinto de "desc" cae a ascendente."""
    column = columns.get(sort_by, columns["name"])
    return column.desc() if sort_dir == "desc" else column.asc()


def _content_match_file_ids(db: Session, owner_id: UUID, q: str) -> List[UUID]:
    """`file_id`s de `owner_id` cuyo CONTENIDO indexado (Ronda 6, ver
    `FileContentIndex`) matchea `q` -- SQL crudo (`text()`) contra
    `search_vector`, la columna generada de Postgres que no se mapea en el
    ORM (ver docstring de `FileContentIndex` para el motivo). `plainto_tsquery`
    con bind param (`:q`), nunca interpolado en el string -- mismo criterio
    anti-injection que el resto del módulo con SQL crudo (`get_descendant_ids`).

    Archivos sin fila en `file_content_index` (todavía no indexados, o
    indexación en 'pending'/'failed'/'unsupported') simplemente no aparecen
    acá -- el `INNER JOIN` los excluye sin necesidad de filtrar por
    `extraction_status` explícitamente (una fila con `content_text` NULL o
    vacío tiene un `search_vector` vacío, que no matchea ningún `tsquery`
    no vacío de todos modos)."""
    if not q or not q.strip():
        return []
    rows = db.execute(
        text(
            """
            SELECT f.id
            FROM files f
            INNER JOIN file_content_index fci ON fci.file_id = f.id
            WHERE f.owner_id = :owner_id
              AND f.deleted_at IS NULL
              AND fci.search_vector @@ plainto_tsquery('spanish', :q)
            """
        ),
        {"owner_id": owner_id, "q": q},
    )
    return [row[0] for row in rows]


class CRUDFolder(CRUDBase[Folder, None, None]):
    def get_active(self, db: Session, folder_id: UUID) -> Optional[Folder]:
        return (
            db.query(Folder)
            .filter(Folder.id == folder_id, Folder.deleted_at.is_(None))
            .first()
        )

    def get_children(
        self,
        db: Session,
        owner_id: UUID,
        parent_id: Optional[UUID],
        sort_by: str = "name",
        sort_dir: str = "asc",
        favorites_only: bool = False,
        tag_id: Optional[UUID] = None,
    ) -> List[Folder]:
        query = db.query(Folder).options(selectinload(Folder.tags)).filter(
            Folder.owner_id == owner_id, Folder.deleted_at.is_(None)
        )
        if parent_id is None:
            query = query.filter(Folder.parent_id.is_(None))
        else:
            query = query.filter(Folder.parent_id == parent_id)
        if favorites_only:
            query = query.filter(Folder.is_favorite.is_(True))
        if tag_id is not None:
            query = query.join(folder_tags, folder_tags.c.folder_id == Folder.id).filter(
                folder_tags.c.tag_id == tag_id
            )
        return query.order_by(_resolve_sort_column(_FOLDER_SORT_COLUMNS, sort_by, sort_dir)).all()

    def get_trash(
        self,
        db: Session,
        owner_id: Optional[UUID],
        sort_by: str = "name",
        sort_dir: str = "asc",
        favorites_only: bool = False,
        tag_id: Optional[UUID] = None,
    ) -> List[Folder]:
        query = db.query(Folder).options(selectinload(Folder.tags)).filter(Folder.deleted_at.isnot(None))
        if owner_id is not None:
            query = query.filter(Folder.owner_id == owner_id)
        if favorites_only:
            query = query.filter(Folder.is_favorite.is_(True))
        if tag_id is not None:
            query = query.join(folder_tags, folder_tags.c.folder_id == Folder.id).filter(
                folder_tags.c.tag_id == tag_id
            )
        return query.order_by(_resolve_sort_column(_FOLDER_SORT_COLUMNS, sort_by, sort_dir)).all()

    def search(
        self,
        db: Session,
        owner_id: UUID,
        q: str,
        sort_by: str = "name",
        sort_dir: str = "asc",
        favorites_only: bool = False,
        tag_id: Optional[UUID] = None,
    ) -> List[Folder]:
        query = db.query(Folder).options(selectinload(Folder.tags)).filter(
            Folder.owner_id == owner_id,
            Folder.deleted_at.is_(None),
            Folder.name.ilike(f"%{q}%"),
        )
        if favorites_only:
            query = query.filter(Folder.is_favorite.is_(True))
        if tag_id is not None:
            query = query.join(folder_tags, folder_tags.c.folder_id == Folder.id).filter(
                folder_tags.c.tag_id == tag_id
            )
        return query.order_by(_resolve_sort_column(_FOLDER_SORT_COLUMNS, sort_by, sort_dir)).all()

    def get_descendant_ids(self, db: Session, folder_id: UUID) -> List[UUID]:
        """Todos los descendientes (subcarpetas) de `folder_id`, incluidos
        borrados -- usado para recorrer el subárbol en delete/restore y para
        la validación anti-ciclo en move.

        Una sola query `WITH RECURSIVE` en vez de un BFS con una query por
        nivel -- en árboles muy anidados el BFS escalaba linealmente en
        cantidad de queries (medido: 3000 carpetas anidadas, 0.6-0.9s por
        operación). El límite de profundidad (`MAX_FOLDER_DEPTH` en
        router.py) ya acota el caso extremo desde `create_folder`, pero esta
        query es más robusta independientemente de ese límite.
        """
        rows = db.execute(
            text(
                """
                WITH RECURSIVE descendants AS (
                    SELECT id, parent_id FROM folders WHERE parent_id = :folder_id
                    UNION ALL
                    SELECT f.id, f.parent_id FROM folders f
                    INNER JOIN descendants d ON f.parent_id = d.id
                )
                SELECT id FROM descendants
                """
            ),
            {"folder_id": folder_id},
        )
        return [row[0] for row in rows]

    def get_subtree_height(self, db: Session, folder_id: UUID) -> int:
        """Altura del subárbol de `folder_id`: 0 si no tiene subcarpetas, N si
        su descendiente más profundo está N niveles debajo. Usado para
        validar `MAX_FOLDER_DEPTH` al MOVER una carpeta (a diferencia de
        crearla, mover puede arrastrar un subárbol entero más profundo que la
        carpeta movida en sí — chequear solo la profundidad de la carpeta
        movida no alcanza, hallazgo del auditor final 2026-09-05)."""
        row = db.execute(
            text(
                """
                WITH RECURSIVE descendants AS (
                    SELECT id, parent_id, 1 AS level FROM folders WHERE parent_id = :folder_id
                    UNION ALL
                    SELECT f.id, f.parent_id, d.level + 1 FROM folders f
                    INNER JOIN descendants d ON f.parent_id = d.id
                )
                SELECT COALESCE(MAX(level), 0) FROM descendants
                """
            ),
            {"folder_id": folder_id},
        ).scalar()
        return int(row or 0)


class CRUDFile(CRUDBase[File, None, None]):
    """Ronda 9 (coordinación de subida multipart + antivirus asíncrono):
    TODOS los métodos de lectura de esta clase -- incluido `get()`, heredado
    de `CRUDBase` pero sobreescrito acá -- filtran `File.scan_status ==
    _VISIBLE_SCAN_STATUS` de forma centralizada. Un archivo 'pending'
    (subida multipart todavía sin escanear) o 'infected' (AV lo marcó como
    amenaza) queda invisible en CUALQUIER lectura que pase por este
    repository -- listados normales, papelera, búsqueda, detalle,
    descarga (`download_file` en app/files/router.py usa `_get_owned_file`,
    que a su vez llama a `get()`), y también al resolver el archivo de un
    share (`file_repo.get_active(db, share.file_id)`) -- ni siquiera el
    propio dueño puede verlo/descargarlo mientras no esté 'clean'.

    Se centraliza acá (un solo lugar) a propósito, en vez de parchear cada
    endpoint de app/files/router.py uno por uno -- ese archivo lo tocan otros
    dos agentes de esta misma ronda en paralelo (AV/infra y frontend no,
    pero el de AV sí construye la tarea que marca 'clean'/'infected'), así
    que modificarlo acá habría sido tanto fuera de alcance como un foco real
    de conflictos de merge. Cubre confirmadamente los 9 call-sites reales de
    `file_repo.*` que existen hoy en toda la app (get/get_active/get_children/
    get_trash/search, ver `app/files/router.py` y
    `app/worker/tasks/indexing.py`) -- verificado con grep antes de este
    cambio, no es una suposición.

    Para el escaneo de AV en sí (que necesita leer un `File` 'pending' para
    poder actualizarlo a 'clean'/'infected'), ver `get_for_scan_worker` más
    abajo -- el ÚNICO método de esta clase que NO aplica este filtro, a
    propósito."""

    def get(self, db: Session, id) -> Optional[File]:
        return (
            db.query(File)
            .filter(File.id == id, File.scan_status == _VISIBLE_SCAN_STATUS)
            .first()
        )

    def get_for_scan_worker(self, db: Session, file_id: UUID) -> Optional[File]:
        """Lectura SIN el filtro de `scan_status` -- exclusivamente para la
        tarea de escaneo asíncrono de AV (Ronda 9, módulo construido en
        paralelo por otro agente de esta misma ronda:
        `app.worker.tasks.av_scan.scan_uploaded_file`), que necesita poder
        leer un `File` recién creado en `'pending'` para poder marcarlo
        `'clean'`/`'infected'` después de escanearlo -- con el filtro
        normal de `get()`, esa tarea jamás encontraría el archivo que tiene
        que procesar. No usar para NADA que sirva contenido a un usuario
        final."""
        return db.query(File).filter(File.id == file_id).first()

    def get_active(self, db: Session, file_id: UUID) -> Optional[File]:
        return (
            db.query(File)
            .filter(File.id == file_id, File.deleted_at.is_(None), File.scan_status == _VISIBLE_SCAN_STATUS)
            .first()
        )

    def get_children(
        self,
        db: Session,
        owner_id: UUID,
        folder_id: Optional[UUID],
        sort_by: str = "name",
        sort_dir: str = "asc",
        favorites_only: bool = False,
        tag_id: Optional[UUID] = None,
    ) -> List[File]:
        query = db.query(File).options(selectinload(File.tags)).filter(
            File.owner_id == owner_id, File.deleted_at.is_(None), File.scan_status == _VISIBLE_SCAN_STATUS
        )
        if folder_id is None:
            query = query.filter(File.folder_id.is_(None))
        else:
            query = query.filter(File.folder_id == folder_id)
        if favorites_only:
            query = query.filter(File.is_favorite.is_(True))
        if tag_id is not None:
            query = query.join(file_tags, file_tags.c.file_id == File.id).filter(
                file_tags.c.tag_id == tag_id
            )
        return query.order_by(_resolve_sort_column(_FILE_SORT_COLUMNS, sort_by, sort_dir)).all()

    def get_trash(
        self,
        db: Session,
        owner_id: Optional[UUID],
        sort_by: str = "name",
        sort_dir: str = "asc",
        favorites_only: bool = False,
        tag_id: Optional[UUID] = None,
    ) -> List[File]:
        query = db.query(File).options(selectinload(File.tags)).filter(
            File.deleted_at.isnot(None), File.scan_status == _VISIBLE_SCAN_STATUS
        )
        if owner_id is not None:
            query = query.filter(File.owner_id == owner_id)
        if favorites_only:
            query = query.filter(File.is_favorite.is_(True))
        if tag_id is not None:
            query = query.join(file_tags, file_tags.c.file_id == File.id).filter(
                file_tags.c.tag_id == tag_id
            )
        return query.order_by(_resolve_sort_column(_FILE_SORT_COLUMNS, sort_by, sort_dir)).all()

    def search(
        self,
        db: Session,
        owner_id: UUID,
        q: str,
        sort_by: str = "name",
        sort_dir: str = "asc",
        favorites_only: bool = False,
        tag_id: Optional[UUID] = None,
    ) -> List[File]:
        """Búsqueda por NOMBRE (ilike, comportamiento original) O por
        CONTENIDO indexado (Ronda 6, ver `_content_match_file_ids`) -- un
        archivo aparece si matchea cualquiera de los dos. Cada resultado
        queda anotado con un atributo `matched_by` en memoria ('name',
        'content' o 'both', ver más abajo) -- NO es una columna del modelo
        `File`, es un atributo plano seteado acá para que `FileOut`
        (`from_attributes=True`) lo recoja sin tener que cambiar el shape de
        ningún otro endpoint que reusa `FileOut`."""
        content_ids = _content_match_file_ids(db, owner_id, q)

        query = db.query(File).options(selectinload(File.tags)).filter(
            File.owner_id == owner_id,
            File.deleted_at.is_(None),
            File.scan_status == _VISIBLE_SCAN_STATUS,
        )
        if content_ids:
            query = query.filter(or_(File.name.ilike(f"%{q}%"), File.id.in_(content_ids)))
        else:
            query = query.filter(File.name.ilike(f"%{q}%"))
        if favorites_only:
            query = query.filter(File.is_favorite.is_(True))
        if tag_id is not None:
            query = query.join(file_tags, file_tags.c.file_id == File.id).filter(
                file_tags.c.tag_id == tag_id
            )
        results = query.order_by(_resolve_sort_column(_FILE_SORT_COLUMNS, sort_by, sort_dir)).all()

        content_id_set = set(content_ids)
        q_lower = q.lower()
        for f in results:
            name_matched = q_lower in f.name.lower()
            content_matched = f.id in content_id_set
            if name_matched and content_matched:
                f.matched_by = "both"
            elif content_matched:
                f.matched_by = "content"
            else:
                f.matched_by = "name"
        return results

    def get_by_folder_ids(self, db: Session, folder_ids: List[UUID]) -> List[File]:
        if not folder_ids:
            return []
        return db.query(File).filter(File.folder_id.in_(folder_ids), File.scan_status == _VISIBLE_SCAN_STATUS).all()


class CRUDFileVersion(CRUDBase[FileVersion, None, None]):
    def get_for_file(self, db: Session, file_id: UUID) -> List[FileVersion]:
        """Historial completo de `file_id`, más reciente primero -- mismo
        orden que expone `GET /files/{id}/versions`."""
        return (
            db.query(FileVersion)
            .filter(FileVersion.file_id == file_id)
            .order_by(FileVersion.version_number.desc())
            .all()
        )

    def get_max_version_number(self, db: Session, file_id: UUID) -> int:
        """Último `version_number` ya usado por `file_id`, 0 si todavía no
        tiene ninguna versión (no debería pasar en la práctica -- `upload_file`
        siempre crea la versión 1 junto con el propio `File`, ver
        `_validate_and_store_upload`). El próximo número a usar es
        SIEMPRE `get_max_version_number(...) + 1`, nunca `len(...) + 1` --
        si alguna vez se admite borrar una versión puntual del historial,
        `len` reusaría números ya usados."""
        result = (
            db.query(func.max(FileVersion.version_number))
            .filter(FileVersion.file_id == file_id)
            .scalar()
        )
        return int(result or 0)

    def get_by_id_for_file(self, db: Session, version_id: UUID, file_id: UUID) -> Optional[FileVersion]:
        """Una versión puntual, validando que pertenezca REALMENTE a
        `file_id` -- 404 en el router si no (nunca confiar en que el cliente
        mande un `version_id` de un archivo ajeno solo porque adivinó el
        UUID, mismo criterio anti-IDOR que el resto del módulo)."""
        return (
            db.query(FileVersion)
            .filter(FileVersion.id == version_id, FileVersion.file_id == file_id)
            .first()
        )

    def get_total_size_for_file(self, db: Session, file_id: UUID) -> int:
        """Cuota real ocupada por `file_id`: suma de `size_bytes` de sus
        blobs ÚNICOS en MinIO, deduplicados por `storage_key` -- NUNCA sumar
        `size_bytes` fila por fila de `file_versions` sin deduplicar (bug
        real encontrado en la revisión adversarial de Ronda 4, 2026-09-20):
        `restore_file_version` crea una fila de historial NUEVA que
        REAPUNTA al `storage_key` de una versión vieja, sin reservar cuota
        nueva (ver su docstring en el router -- es a propósito, el blob ya
        estaba contado). Sumar por fila en vez de por blob único cuenta ESE
        mismo blob dos veces, inflando cuánto libera la purga y arrastrando
        cuota de OTROS archivos del mismo dueño que nunca se tocaron.

        `MIN(size_bytes)` en el `GROUP BY storage_key` es arbitrario a
        propósito -- todas las filas que comparten un `storage_key` tienen,
        por construcción, el mismo `size_bytes` (apuntan al mismo blob
        real), así que cualquier función de agregación de un solo valor da
        el mismo resultado."""
        per_blob = (
            db.query(
                FileVersion.storage_key,
                func.min(FileVersion.size_bytes).label("size_bytes"),
            )
            .filter(FileVersion.file_id == file_id)
            .group_by(FileVersion.storage_key)
            .subquery()
        )
        result = db.query(func.coalesce(func.sum(per_blob.c.size_bytes), 0)).scalar()
        return int(result or 0)


class CRUDShare(CRUDBase[Share, None, None]):
    def get_by_token(self, db: Session, token: str) -> Optional[Share]:
        return db.query(Share).filter(Share.token == token).first()

    def get_for_file(self, db: Session, file_id: UUID) -> List[Share]:
        return (
            db.query(Share)
            .filter(Share.file_id == file_id)
            .order_by(Share.created_at.desc())
            .all()
        )

    def get_for_folder(self, db: Session, folder_id: UUID) -> List[Share]:
        return (
            db.query(Share)
            .filter(Share.folder_id == folder_id)
            .order_by(Share.created_at.desc())
            .all()
        )

    def get_for_recipient(self, db: Session, user_id: UUID) -> List[Share]:
        """Shares dirigidos a `user_id` (Ronda 3) -- incluye revocados/
        expirados (mismo criterio que `get_for_file`/`get_for_folder`: se
        muestra el historial completo, `is_active` en `ShareOut` distingue
        cuáles siguen vigentes)."""
        return (
            db.query(Share)
            .filter(Share.shared_with_user_id == user_id)
            .order_by(Share.created_at.desc())
            .all()
        )


class CRUDFileContentIndex(CRUDBase[FileContentIndex, None, None]):
    """No hereda el `get(db, id)` genérico de `CRUDBase` tal cual -- asume
    una columna `id`, y la PK real de este modelo es `file_id` (relación 1:1
    con `File`, ver docstring de `FileContentIndex`)."""

    def get_by_file_id(self, db: Session, file_id: UUID) -> Optional[FileContentIndex]:
        return db.query(FileContentIndex).filter(FileContentIndex.file_id == file_id).first()

    def upsert(
        self,
        db: Session,
        file_id: UUID,
        *,
        content_text: Optional[str],
        extraction_status: str,
        error_message: Optional[str] = None,
    ) -> FileContentIndex:
        """Reemplaza (o crea) la fila de índice de `file_id` -- relación 1:1,
        SIEMPRE refleja la extracción MÁS RECIENTE. Usado por
        `app.worker.tasks.indexing.index_file_content` -- nunca conserva el
        `content_text` de una extracción vieja cuando el contenido del
        archivo cambió (versión nueva, restore, reemplazo vía share)."""
        record = self.get_by_file_id(db, file_id)
        if record is None:
            record = FileContentIndex(file_id=file_id)
            db.add(record)
        record.content_text = content_text
        record.extraction_status = extraction_status
        record.error_message = error_message
        record.indexed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(record)
        return record


folder_repo = CRUDFolder(Folder)
file_repo = CRUDFile(File)
file_version_repo = CRUDFileVersion(FileVersion)
share_repo = CRUDShare(Share)
file_content_index_repo = CRUDFileContentIndex(FileContentIndex)
