"""CRUD de Carpetas y Archivos.

Router-heavy por convención del proyecto (ver notifications/access_control):
esta capa solo hace queries, la lógica de negocio (permisos duales,
detección de ciclos, recursión de papelera) vive en router.py.
"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.files.models import File, Folder, Share
from app.shared.repository_base import CRUDBase


class CRUDFolder(CRUDBase[Folder, None, None]):
    def get_active(self, db: Session, folder_id: UUID) -> Optional[Folder]:
        return (
            db.query(Folder)
            .filter(Folder.id == folder_id, Folder.deleted_at.is_(None))
            .first()
        )

    def get_children(
        self, db: Session, owner_id: UUID, parent_id: Optional[UUID]
    ) -> List[Folder]:
        query = db.query(Folder).filter(
            Folder.owner_id == owner_id, Folder.deleted_at.is_(None)
        )
        if parent_id is None:
            query = query.filter(Folder.parent_id.is_(None))
        else:
            query = query.filter(Folder.parent_id == parent_id)
        return query.order_by(Folder.name).all()

    def get_trash(self, db: Session, owner_id: Optional[UUID]) -> List[Folder]:
        query = db.query(Folder).filter(Folder.deleted_at.isnot(None))
        if owner_id is not None:
            query = query.filter(Folder.owner_id == owner_id)
        return query.order_by(Folder.name).all()

    def search(self, db: Session, owner_id: UUID, q: str) -> List[Folder]:
        return (
            db.query(Folder)
            .filter(
                Folder.owner_id == owner_id,
                Folder.deleted_at.is_(None),
                Folder.name.ilike(f"%{q}%"),
            )
            .order_by(Folder.name)
            .all()
        )

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
    def get_active(self, db: Session, file_id: UUID) -> Optional[File]:
        return (
            db.query(File)
            .filter(File.id == file_id, File.deleted_at.is_(None))
            .first()
        )

    def get_children(
        self, db: Session, owner_id: UUID, folder_id: Optional[UUID]
    ) -> List[File]:
        query = db.query(File).filter(
            File.owner_id == owner_id, File.deleted_at.is_(None)
        )
        if folder_id is None:
            query = query.filter(File.folder_id.is_(None))
        else:
            query = query.filter(File.folder_id == folder_id)
        return query.order_by(File.name).all()

    def get_trash(self, db: Session, owner_id: Optional[UUID]) -> List[File]:
        query = db.query(File).filter(File.deleted_at.isnot(None))
        if owner_id is not None:
            query = query.filter(File.owner_id == owner_id)
        return query.order_by(File.name).all()

    def search(self, db: Session, owner_id: UUID, q: str) -> List[File]:
        return (
            db.query(File)
            .filter(
                File.owner_id == owner_id,
                File.deleted_at.is_(None),
                File.name.ilike(f"%{q}%"),
            )
            .order_by(File.name)
            .all()
        )

    def get_by_folder_ids(self, db: Session, folder_ids: List[UUID]) -> List[File]:
        if not folder_ids:
            return []
        return db.query(File).filter(File.folder_id.in_(folder_ids)).all()


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


folder_repo = CRUDFolder(Folder)
file_repo = CRUDFile(File)
share_repo = CRUDShare(Share)
