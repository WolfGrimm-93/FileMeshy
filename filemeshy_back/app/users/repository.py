from sqlalchemy.orm import Session, joinedload
from app.shared.repository_base import CRUDBase
from app.users.models import User
from app.users.schemas import UserCreate, UserUpdate
from app.core.security import verify_password
from typing import Optional, Dict, Any

# Hash bcrypt fijo (de un valor arbitrario, no una contraseña real de nadie),
# usado SOLO para que authenticate() haga el mismo trabajo de CPU cuando el
# email no existe -- ver el docstring de authenticate() para el motivo
# (defensa contra enumeración de emails por timing).
_DUMMY_HASH_FOR_TIMING = "$2b$12$DubReTSocL8KcKAciiarFOc0/51JYfH9MJh7UH.d0nIUzvIETuaQ2"


class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    """CRUD operations para usuarios -- solo acceso a datos.

    La lógica que cruza a access_control (normalización/recalculo de permisos
    al crear o actualizar un usuario) vive en app/users/service.py, no acá --
    ver Riesgo #1 de RECON_RIESGOS.md ("crud/user.py llama hoy a
    access_control.service.permission_mapper directo").
    """

    def get(self, db: Session, id: Any) -> Optional[User]:  # type: ignore[override]
        """Obtiene un usuario por ID (con role_obj cargado)."""
        return db.query(User).options(joinedload(User.role_obj)).filter(User.id == id).first()

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        """Obtiene un usuario por email (con role_obj cargado)."""
        return db.query(User).options(joinedload(User.role_obj)).filter(User.email == email).first()

    def insert(
        self,
        db: Session,
        *,
        email: str,
        hashed_password: str,
        first_name: str,
        last_name: Optional[str],
        phone: Optional[str],
        role_id,
        is_active: bool,
        permissions: list,
    ) -> User:
        """Inserta un usuario ya con todos sus campos resueltos (password
        hasheada, role_id resuelto, permissions ya normalizados) -- la
        resolución de esos valores es responsabilidad de users/service.py."""
        db_obj = User(
            email=email,
            hashed_password=hashed_password,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role_id=role_id,
            is_active=is_active,
            permissions=permissions,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def apply_fields(self, db: Session, db_obj: User, update_data: Dict[str, Any]) -> User:
        """Aplica un dict de campos ya resueltos (password ya hasheada,
        permissions ya normalizados/recalculados) -- esa resolución es
        responsabilidad de users/service.py."""
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def authenticate(
        self,
        db: Session,
        email: str,
        password: str
    ) -> Optional[User]:
        """Autentica un usuario con email y contraseña.

        Tiempo de respuesta equivalente exista o no el email: antes, un email
        inexistente retornaba de inmediato (sin correr bcrypt), mientras que uno
        existente con password incorrecta corría verify_password (~100ms) --
        esa diferencia de orden de magnitud permite enumerar emails válidos por
        timing sin necesitar ninguna otra señal. Corriendo verify_password
        siempre (contra un hash bcrypt fijo cuando el usuario no existe), los
        dos casos hacen el mismo trabajo de CPU antes de responder.
        """
        user = self.get_by_email(db, email=email)
        if not user:
            verify_password(password, _DUMMY_HASH_FOR_TIMING)
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    def is_active(self, user: User) -> bool:
        """Verifica si un usuario está activo."""
        return user.is_active

    def is_superuser(self, user: User) -> bool:
        """Verifica si un usuario tiene el rol SUPER_ADMIN."""
        return bool(user.role_obj and user.role_obj.name == 'SUPER_ADMIN')


# Instancia global
user = CRUDUser(User)
