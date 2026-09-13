"""CRUD base generico, reutilizable por el repository.py de cualquier modulo.

Extraido de app/crud/base.py durante la migracion a monolito modular -- es
infraestructura tecnica sin logica de negocio propia (ningun modulo es su
"dueno" real), por eso vive en shared/ en vez de dentro de alguno de los 10
modulos de negocio. Antes de moverlo se re-grepeo el estado actual del repo
(no la lista vieja del manifiesto, que todavia mencionaba crud/user.py) para
encontrar a TODOS los importadores reales: app/crud/audit_log.py,
app/crud/configuration.py y app/users/repository.py (ya migrado por el
Implementador 1) -- los tres actualizados para apuntar aca.
"""
from typing import Generic, TypeVar, List, Type, Optional, Any
from sqlalchemy.orm import Session
from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """CRUD base genérico para todas las operaciones."""

    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, db: Session, id: Any) -> Optional[ModelType]:
        """Obtiene un registro por ID."""
        return db.query(self.model).filter(self.model.id == id).first()

    def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Obtiene todos los registros."""
        return db.query(self.model).offset(skip).limit(limit).all()

    def create(self, db: Session, obj_in: CreateSchemaType) -> ModelType:
        """Crea un nuevo registro."""
        obj_data = obj_in.model_dump()
        db_obj = self.model(**obj_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self,
        db: Session,
        db_obj: ModelType,
        obj_in: UpdateSchemaType
    ) -> ModelType:
        """Actualiza un registro."""
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, id: Any) -> Optional[ModelType]:
        """Elimina un registro."""
        obj = db.query(self.model).get(id)
        if obj:
            db.delete(obj)
            db.commit()
        return obj

    def exists(self, db: Session, **kwargs) -> bool:
        """Verifica si existe un registro con los filtros dados."""
        return db.query(self.model.id).filter_by(**kwargs).first() is not None
