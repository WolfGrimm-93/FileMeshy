"""CRUD de Tag (etiquetas personales).

Router-heavy por convención del proyecto (ver files/notifications): esta
capa solo hace queries -- ownership y las reglas de negocio (nombre
duplicado, validar que un set de ids pertenezca todo al mismo dueño) viven
en tags/router.py y en los endpoints PUT .../tags de app/files/router.py.
"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.shared.repository_base import CRUDBase
from app.tags.models import Tag


class CRUDTag(CRUDBase[Tag, None, None]):
    def get_by_owner(self, db: Session, owner_id: UUID) -> List[Tag]:
        return (
            db.query(Tag)
            .filter(Tag.owner_id == owner_id)
            .order_by(Tag.name.asc())
            .all()
        )

    def get_by_name(self, db: Session, owner_id: UUID, name: str) -> Optional[Tag]:
        return (
            db.query(Tag)
            .filter(Tag.owner_id == owner_id, Tag.name == name)
            .first()
        )

    def get_by_ids_for_owner(self, db: Session, owner_id: UUID, tag_ids: List[UUID]) -> List[Tag]:
        """Etiquetas de `tag_ids` que ADEMÁS pertenecen a `owner_id` -- el
        caller (router) compara `len()` contra el pedido original para
        detectar cualquier id ajeno o inexistente (criterio "todo o nada":
        nunca se aplica un subconjunto silencioso, ver
        `_resolve_owned_tags` en app/files/router.py)."""
        if not tag_ids:
            return []
        return (
            db.query(Tag)
            .filter(Tag.owner_id == owner_id, Tag.id.in_(tag_ids))
            .all()
        )


tag_repo = CRUDTag(Tag)
