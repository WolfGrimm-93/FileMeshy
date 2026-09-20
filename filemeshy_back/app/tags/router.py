"""Router de Tags -- etiquetas personales del usuario autenticado.

Montado bajo `/tags` en app/api/v1/router.py. Ownership estricto por
`owner_id == current_user.id`, SIN la excepción de admin que sí tiene el
resto de app/files/router.py (una etiqueta es una preferencia personal de
organización, no un recurso administrable cross-usuario -- no hay caso de
uso donde un admin necesite renombrar/borrar la etiqueta "Trabajo" de otro
usuario).

Gate de permiso: `tags.manage` (nuevo, ver app/core/permissions.py),
otorgado por defecto a USER y ADMIN -- gestionar las propias etiquetas es
uso básico del Drive, mismo criterio que `files.view`/`folders.view`."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access_control.service import has_permission
from app.core.database import get_db
from app.tags.models import Tag
from app.tags.repository import tag_repo
from app.tags.schemas import TagCreate, TagOut, TagUpdate
from app.users.models import User

router = APIRouter()


def _get_owned_tag(db: Session, tag_id: UUID, current_user: User) -> Tag:
    """Busca una etiqueta por id verificando ownership. 404 si no existe o es
    de otro usuario -- mismo criterio "no filtrar por qué" que el resto del
    proyecto (ver app/files/router.py::_get_owned_file)."""
    tag = tag_repo.get(db, tag_id)
    if not tag or tag.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Etiqueta no encontrada")
    return tag


@router.get("", response_model=List[TagOut])
def list_tags(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["tags.manage"])),
):
    """Etiquetas del usuario actual -- solo las suyas, nunca las de otro
    usuario (scoping por `owner_id`, no hay vista cross-usuario ni para
    admin)."""
    return tag_repo.get_by_owner(db, current_user.id)


@router.post("", response_model=TagOut, status_code=status.HTTP_201_CREATED)
def create_tag(
    payload: TagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["tags.manage"])),
):
    if tag_repo.get_by_name(db, current_user.id, payload.name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una etiqueta con ese nombre",
        )

    tag = Tag(owner_id=current_user.id, name=payload.name, color=payload.color)
    db.add(tag)
    try:
        db.commit()
    except IntegrityError:
        # Ventana de carrera entre el chequeo de arriba y el commit (dos
        # requests concurrentes del mismo usuario con el mismo nombre) -- el
        # constraint único real (uq_tag_owner_name) es la garantía de fondo,
        # el chequeo previo solo cubre el caso común con un mensaje claro.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una etiqueta con ese nombre",
        )
    db.refresh(tag)
    return tag


@router.patch("/{tag_id}", response_model=TagOut)
def update_tag(
    tag_id: UUID,
    payload: TagUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["tags.manage"])),
):
    tag = _get_owned_tag(db, tag_id, current_user)
    fields_set = payload.model_fields_set

    if "name" in fields_set and payload.name is not None and payload.name != tag.name:
        if tag_repo.get_by_name(db, current_user.id, payload.name) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe una etiqueta con ese nombre",
            )
        tag.name = payload.name

    if "color" in fields_set:
        # Campo presente (incluido `null` explícito) = valor nuevo, borra el
        # color actual si vino `null` -- mismo mecanismo de `model_fields_set`
        # que el resto del proyecto (ver FileUpdate.is_favorite).
        tag.color = payload.color

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una etiqueta con ese nombre",
        )
    db.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    tag_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission(["tags.manage"])),
):
    """Borra la etiqueta. La cascada de BD (`ondelete=CASCADE` en
    `file_tags`/`folder_tags`) saca automáticamente las filas de vínculo --
    no hace falta desasignarla a mano de cada archivo/carpeta antes."""
    tag = _get_owned_tag(db, tag_id, current_user)
    db.delete(tag)
    db.commit()
    return None
