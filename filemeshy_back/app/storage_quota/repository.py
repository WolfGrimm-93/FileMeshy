"""CRUD de cuotas de almacenamiento.

Los incrementos/decrementos de `bytes_used` usan SQL directo (`UPDATE ...
SET bytes_used = bytes_used + :delta`, o el `INSERT ... ON CONFLICT` de más
abajo cuando la fila puede no existir todavía) en vez de leer-modificar-guardar
en Python -- con uploads concurrentes del mismo usuario, dos requests que leen
el mismo valor y lo pisan al guardar pierden un incremento; el UPDATE atómico
de Postgres no tiene esa ventana."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.repository_base import CRUDBase
from app.shared.utils.uuid7 import uuid7
from app.storage_quota.models import UserStorageQuota


class CRUDUserStorageQuota(CRUDBase[UserStorageQuota, None, None]):
    def get_by_user_id(self, db: Session, user_id: UUID) -> Optional[UserStorageQuota]:
        return db.query(UserStorageQuota).filter(UserStorageQuota.user_id == user_id).first()

    def get_by_user_ids(self, db: Session, user_ids: List[UUID]) -> List[UserStorageQuota]:
        if not user_ids:
            return []
        return db.query(UserStorageQuota).filter(UserStorageQuota.user_id.in_(user_ids)).all()

    def adjust_bytes_used(self, db: Session, user_id: UUID, delta: int) -> None:
        """Suma (`delta` positivo, upload) o resta (`delta` negativo, purge)
        de forma atómica. Crea la fila perezosamente (`limit_bytes=NULL`) si
        el usuario todavía no tenía una -- `ON CONFLICT` en vez de un
        SELECT-then-INSERT previo, para que la creación y el ajuste sean un
        único statement atómico (sin ventana de carrera entre ambos pasos).
        `GREATEST(..., 0)` evita que un decremento deje el contador negativo
        por drift (ej. dos purgas del mismo archivo por una reejecución de
        la tarea)."""
        db.execute(
            text(
                """
                INSERT INTO user_storage_quotas (id, user_id, limit_bytes, bytes_used, updated_at)
                VALUES (:id, :user_id, NULL, GREATEST(:delta, 0), now())
                ON CONFLICT (user_id) DO UPDATE
                SET bytes_used = GREATEST(user_storage_quotas.bytes_used + :delta, 0),
                    updated_at = now()
                """
            ),
            {"id": uuid7(), "user_id": user_id, "delta": delta},
        )
        db.commit()

    def reserve_bytes_or_fail(self, db: Session, user_id: UUID, additional_bytes: int) -> bool:
        """Chequeo de límite + reserva del cupo en UNA sola operación atómica
        -- a diferencia de `adjust_bytes_used`, esta SÍ valida `limit_bytes`
        antes de sumar. Usar ANTES de subir a MinIO (ver
        app/files/router.py::upload_file); si devuelve False, no se sube
        nada. Cierra la ventana de carrera que tenía el diseño anterior
        (SELECT de chequeo separado del UPDATE de incremento, con la subida
        a MinIO en el medio): dos uploads concurrentes del mismo usuario,
        cada uno por debajo del remanente visto en su propio SELECT, podían
        pasar el chequeo por separado y sumados superar `limit_bytes`
        (hallazgo de la revisión adversarial, Fase 3, 2026-09-08).

        `INSERT ... ON CONFLICT (user_id) DO UPDATE ... WHERE <guard>`: si el
        usuario no tenía fila todavía, el INSERT siempre aplica (fila nueva,
        `limit_bytes=NULL` = sin límite, la reserva no puede superarlo). Si
        ya tenía fila, el UPDATE del conflicto solo se ejecuta si el guard es
        verdadero -- Postgres documenta que un WHERE falso en `DO UPDATE`
        deja la fila EXISTENTE intacta, sin error y sin afectar ninguna fila
        (`rowcount` queda en 0), que es exactamente la señal que se necesita
        para distinguir "reservado" de "límite superado" sin un SELECT previo.

        Si la reserva se aplica pero la subida a MinIO falla después, el
        caller tiene que compensar con `adjust_bytes_used(db, user_id,
        -additional_bytes)` -- esta función no sabe si la subida va a tener
        éxito, solo reserva el cupo."""
        result = db.execute(
            text(
                """
                INSERT INTO user_storage_quotas (id, user_id, limit_bytes, bytes_used, updated_at)
                VALUES (:id, :user_id, NULL, GREATEST(:delta, 0), now())
                ON CONFLICT (user_id) DO UPDATE
                SET bytes_used = user_storage_quotas.bytes_used + :delta,
                    updated_at = now()
                WHERE user_storage_quotas.limit_bytes IS NULL
                   OR user_storage_quotas.bytes_used + :delta <= user_storage_quotas.limit_bytes
                """
            ),
            {"id": uuid7(), "user_id": user_id, "delta": additional_bytes},
        )
        db.commit()
        return result.rowcount > 0

    def upsert_limit(self, db: Session, user_id: UUID, limit_bytes: Optional[int]) -> UserStorageQuota:
        """Fija `limit_bytes` (PUT del admin). Crea la fila con `bytes_used=0`
        si no existía -- mismo patrón `ON CONFLICT` atómico que arriba."""
        db.execute(
            text(
                """
                INSERT INTO user_storage_quotas (id, user_id, limit_bytes, bytes_used, updated_at)
                VALUES (:id, :user_id, :limit_bytes, 0, now())
                ON CONFLICT (user_id) DO UPDATE
                SET limit_bytes = :limit_bytes, updated_at = now()
                """
            ),
            {"id": uuid7(), "user_id": user_id, "limit_bytes": limit_bytes},
        )
        db.commit()
        return self.get_by_user_id(db, user_id)


user_storage_quota_repo = CRUDUserStorageQuota(UserStorageQuota)
