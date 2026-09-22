"""CRUD de `UploadSession` (Ronda 9).

Router-heavy... no, acá SÍ hay lógica real en el servicio (`app/uploads/service.py`,
coordina MinIO + cuota + admisión) -- este módulo se limita a queries/statements
puros, mismo criterio que `app/backups/repository.py`.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.shared.repository_base import CRUDBase
from app.uploads.models import UploadSession


class CRUDUploadSession(CRUDBase[UploadSession, None, None]):
    def get_owned(self, db: Session, session_id: UUID, owner_id: UUID) -> Optional[UploadSession]:
        """Sesión por id, validando ownership en la misma query -- 404 en el
        service si no matchea (nunca revelar con un 403 que el id existe
        pero es de otro usuario, mismo criterio anti-IDOR que
        `app/files/router.py::_get_owned_file`)."""
        return (
            db.query(UploadSession)
            .filter(UploadSession.id == session_id, UploadSession.owner_id == owner_id)
            .first()
        )

    def count_in_progress(self, db: Session) -> int:
        """Cuenta GLOBAL (no por usuario) de sesiones `'in_progress'` --
        usado como fallback de admisión cuando Redis no está disponible (ver
        `app/uploads/service.py::_try_reserve_admission_slot`). El límite
        (`settings.MAX_CONCURRENT_LARGE_UPLOADS`) protege el I/O de disco de
        MinIO, no es por-usuario."""
        return (
            db.query(UploadSession)
            .filter(UploadSession.status == "in_progress")
            .count()
        )

    def count_in_progress_for_user(self, db: Session, owner_id: UUID) -> int:
        """Cuenta POR USUARIO de sesiones `'in_progress'` -- fallback de
        admisión cuando Redis no está disponible, mismo criterio que
        `count_in_progress` mas el filtro de `owner_id`. Agregado tras la
        revisión adversarial de seguridad (Ronda 9): sin un tope por
        usuario, un solo usuario podía acaparar todo el cupo GLOBAL abriendo
        sesiones sin completar/abortar -- ver
        `settings.MAX_CONCURRENT_LARGE_UPLOADS_PER_USER`."""
        return (
            db.query(UploadSession)
            .filter(UploadSession.status == "in_progress", UploadSession.owner_id == owner_id)
            .count()
        )

    def get_expired_in_progress(self, db: Session, *, now: datetime, limit: int = 200) -> List[UploadSession]:
        """Sesiones `'in_progress'` cuyo `expires_at` ya pasó -- candidatas a
        limpieza (ver `app/worker/tasks/uploads.py`). `limit` acota el batch
        por corrida, mismo criterio defensivo que el resto de tareas
        periódicas del proyecto no quiso arriesgar (ninguna hoy pagina, pero
        esta sí porque una corrida que se cae a mitad de un batch gigante deja
        multipart uploads reales sin abortar en MinIO -- mejor iterar en
        tandas chicas y dejar el resto para la corrida siguiente, 6hs
        después no importa)."""
        return (
            db.query(UploadSession)
            .filter(UploadSession.status == "in_progress", UploadSession.expires_at < now)
            .limit(limit)
            .all()
        )

    def mark_aborted(self, db: Session, session: UploadSession) -> UploadSession:
        session.status = "aborted"
        session.quota_reserved_bytes = 0
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def mark_failed(self, db: Session, session: UploadSession, *, error_message: Optional[str] = None) -> UploadSession:
        session.status = "failed"
        session.quota_reserved_bytes = 0
        if error_message:
            session.last_error = error_message[:2000]
        db.add(session)
        db.commit()
        db.refresh(session)
        return session


upload_session_repo = CRUDUploadSession(UploadSession)
