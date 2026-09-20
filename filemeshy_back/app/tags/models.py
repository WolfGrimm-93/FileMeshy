"""Modelo de Etiqueta (Tag) -- personal, no compartida entre usuarios.

Las etiquetas son un recurso propio del usuario (`owner_id`), no del
archivo/carpeta -- dos usuarios pueden tener cada uno una etiqueta llamada
"Trabajo" sin colisionar (el constraint único es `(owner_id, name)`, no
`name` a secas). El vínculo con archivos/carpetas es muchos-a-muchos vía las
tablas puente `file_tags`/`folder_tags` de más abajo, ambas SIN modelo ORM
propio (son tablas de asociación puras -- ver `Tag.files`/`Tag.folders` y
los `back_populates` correspondientes en `app/files/models.py::File.tags` /
`Folder.tags`)."""

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.shared.utils.uuid7 import uuid7


# Tablas puente puras -- sin modelo ORM propio, solo la PK compuesta y las
# dos FK con CASCADE (borrar el archivo/carpeta o la etiqueta se lleva
# automáticamente la fila de vínculo, sin dejar huérfanos).
file_tags = Table(
    "file_tags",
    Base.metadata,
    Column("file_id", UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

folder_tags = Table(
    "folder_tags",
    Base.metadata,
    Column("folder_id", UUID(as_uuid=True), ForeignKey("folders.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    """Etiqueta personal de un usuario -- nunca compartida entre usuarios
    (ownership por `owner_id`; no existe noción de etiqueta "de equipo" en
    este hito). `(owner_id, name)` es único: un mismo usuario no puede tener
    dos etiquetas con el mismo nombre, pero dos usuarios distintos sí pueden
    llamar a las suyas igual."""

    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_tag_owner_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(50), nullable=False)
    # Hex tipo "#RRGGBB" o nombre de color -- a elección del frontend, sin
    # validación de formato en el backend (mismo criterio "texto libre" que
    # el resto de campos cosméticos del proyecto).
    color = Column(String(20), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    owner = relationship("User", foreign_keys=[owner_id], lazy="select")
    files = relationship("File", secondary=file_tags, back_populates="tags", lazy="select")
    folders = relationship("Folder", secondary=folder_tags, back_populates="tags", lazy="select")
