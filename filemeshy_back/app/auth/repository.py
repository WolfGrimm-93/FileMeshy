"""Acceso a datos de auth: códigos de reset de contraseña y sesiones opacas
de reset de contraseña."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID
from datetime import datetime, timedelta, timezone
import random
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.models import PasswordResetSession
from app.auth.service import CodeHashService

if TYPE_CHECKING:  # solo para anotaciones (código legado, ver nota de CRUDPasswordReset)
    from app.auth.models import PasswordResetCode


class CRUDPasswordReset:
    """CRUD para códigos de restablecimiento de contraseña.

    NOTA: migrado tal cual desde app/crud/password_reset.py -- ese archivo ya
    estaba roto hoy (importaba `PasswordResetCode` desde app.models.password_reset,
    que nunca definió esa clase como modelo de BD, solo existe como schema
    Pydantic en app/schemas/password_reset.py). Sin importadores detectados en
    el repo real (RECON_RIESGOS.md #6) -- se migra igual de roto (el import de
    `PasswordResetCode` queda diferido dentro de cada método, no a nivel de
    módulo, para no arrastrar ese ImportError a CRUDPasswordResetSession de
    abajo, que sí está en uso real). No se arregla acá -- decisión de negocio
    aparte, fuera de alcance de esta migración.
    """

    def create_code(self, db: Session, user_id: UUID, email: str) -> "PasswordResetCode":
        """Crea un nuevo código de reset."""
        from app.auth.models import PasswordResetCode

        # Generar código aleatorio de 6 dígitos
        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])

        # Invalidar códigos anteriores del mismo usuario
        db.query(PasswordResetCode).filter(
            PasswordResetCode.user_id == user_id,
            PasswordResetCode.is_used == False
        ).update({"is_used": True})

        # Crear nuevo código con expiración de 30 minutos
        db_obj = PasswordResetCode(
            user_id=user_id,
            email=email,
            code=code,
            expires_at=datetime.utcnow() + timedelta(minutes=30),
            is_used=False
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_by_code_and_email(
        self, db: Session, code: str, email: str
    ) -> "PasswordResetCode | None":
        """Obtiene un código por código y email."""
        from app.auth.models import PasswordResetCode

        return db.query(PasswordResetCode).filter(
            PasswordResetCode.code == code,
            PasswordResetCode.email == email,
            PasswordResetCode.is_used == False
        ).first()

    def mark_as_used(self, db: Session, reset_code: "PasswordResetCode") -> None:
        """Marca un código como usado."""
        reset_code.is_used = True
        db.commit()

    def delete_expired(self, db: Session) -> int:
        """Elimina códigos expirados. Retorna cantidad eliminada."""
        from app.auth.models import PasswordResetCode

        result = db.query(PasswordResetCode).filter(
            PasswordResetCode.expires_at < datetime.utcnow()
        ).delete()
        db.commit()
        return result


password_reset = CRUDPasswordReset()


class CRUDPasswordResetSession:
    """CRUD para PasswordResetSession."""

    @staticmethod
    def create_session(
        db: Session,
        user_id: UUID,
        email: str,
        code: str,
        expires_in_minutes: int = 15
    ) -> PasswordResetSession:
        """
        Crea una nueva sesión de reset.

        Args:
            db: Sesión de BD
            user_id: ID del usuario
            email: Email del usuario
            code: Código generado (plano, será hasheado aquí)
            expires_in_minutes: Duración de la sesión (default 15 min)

        Returns:
            Sesión creada
        """
        session_id = CodeHashService.generate_session_id()
        code_hash = CodeHashService.hash_code(code)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)

        session = PasswordResetSession(
            session_id=session_id,
            user_id=user_id,
            email=email,
            code_hash=code_hash,
            expires_at=expires_at
        )

        db.add(session)
        db.commit()
        db.refresh(session)

        return session

    @staticmethod
    def get_by_session_id(db: Session, session_id: str) -> PasswordResetSession | None:
        """Obtiene sesión por session_id."""
        return db.query(PasswordResetSession).filter(
            PasswordResetSession.session_id == session_id
        ).first()

    @staticmethod
    def get_by_user_id(db: Session, user_id: UUID) -> PasswordResetSession | None:
        """Obtiene la sesión activa más reciente de un usuario."""
        return db.query(PasswordResetSession).filter(
            PasswordResetSession.user_id == user_id,
            PasswordResetSession.is_used == False
        ).order_by(PasswordResetSession.created_at.desc()).first()

    @staticmethod
    def verify_code(
        db: Session,
        session_id: str,
        code: str,
        max_attempts: int = 5
    ) -> tuple[bool, str]:
        """
        Verifica un código contra la sesión.

        Args:
            db: Sesión de BD
            session_id: ID de la sesión
            code: Código ingresado por el usuario
            max_attempts: Máximo de intentos fallidos

        Returns:
            (is_valid, message) - Tupla con resultado y descripción
        """
        # Ronda 12c (ALTO-1): el intento se CONSUME con un UPDATE atómico condicional
        # ANTES de comparar el código. Antes se leía code_attempts en Python y se
        # incrementaba después: N requests concurrentes leían el mismo valor y
        # todos comparaban (reproducido en vivo: 16 comparaciones con límite 5).
        # Con el UPDATE ... WHERE code_attempts < :max, Postgres serializa por fila y
        # el total de comparaciones efectivas por sesión nunca supera `max_attempts`.
        claimed = db.execute(
            text(
                "UPDATE password_reset_sessions SET code_attempts = COALESCE(code_attempts, 0) + 1 "
                "WHERE session_id = :s AND COALESCE(code_attempts, 0) < :m "
                "AND COALESCE(code_verified, false) = false AND COALESCE(is_used, false) = false "
                "AND expires_at > now() RETURNING code_attempts"
            ),
            {"s": session_id, "m": max_attempts},
        ).first()
        db.commit()

        if claimed is None:
            session = CRUDPasswordResetSession.get_by_session_id(db, session_id)
            if not session:
                return False, "Sesión no encontrada"
            if session.is_expired():
                return False, "Sesión expirada"
            if session.code_verified:
                return False, "Código ya fue verificado"
            if session.is_used:
                return False, "Sesión ya fue utilizada"
            return False, f"Máximo de intentos alcanzado ({max_attempts})"

        attempts = int(claimed[0])
        session = CRUDPasswordResetSession.get_by_session_id(db, session_id)
        db.refresh(session)

        # Validar formato del código (6 dígitos) -- el intento ya fue consumido
        if not code or not code.isdigit() or len(code) != 6:
            return False, "Código inválido (debe ser 6 dígitos)"

        # Validar contra hash
        if not CodeHashService.verify_code(code, session.code_hash):
            return False, f"Código incorrecto ({max(0, max_attempts - attempts)} intentos restantes)"

        # ✅ Código válido: marcar como verificado (condicional: una sola vez)
        verified = db.execute(
            text(
                "UPDATE password_reset_sessions SET code_verified = true "
                "WHERE session_id = :s AND COALESCE(code_verified, false) = false "
                "AND COALESCE(is_used, false) = false RETURNING id"
            ),
            {"s": session_id},
        ).first()
        db.commit()
        if verified is None:
            return False, "Código ya fue verificado"

        return True, "Código verificado correctamente"

    @staticmethod
    def claim_for_confirm(db: Session, session_id: str, user_id: UUID) -> bool:
        """Ronda 12c (MEDIO-3): reclama el uso ÚNICO de la sesión con un UPDATE
        condicional atómico (sin commit: queda en la transacción del cambio de
        contraseña; un /confirm concurrente espera el lock de fila y luego ve
        is_used=true). Además marca como usadas TODAS las demás sesiones de reset
        pendientes del mismo usuario (un token verificado en otra sesión ya no
        sirve). Devuelve False si otro /confirm ya la consumió."""
        row = db.execute(
            text(
                "UPDATE password_reset_sessions SET is_used = true "
                "WHERE session_id = :s AND COALESCE(is_used, false) = false "
                "AND COALESCE(code_verified, false) = true AND expires_at > now() RETURNING id"
            ),
            {"s": session_id},
        ).first()
        if row is None:
            return False
        db.execute(
            text(
                "UPDATE password_reset_sessions SET is_used = true "
                "WHERE user_id = :u AND COALESCE(is_used, false) = false"
            ),
            {"u": user_id},
        )
        return True

    @staticmethod
    def mark_used(db: Session, session_id: str) -> None:
        """Marca la sesión como usada (después de cambiar password)."""
        session = CRUDPasswordResetSession.get_by_session_id(db, session_id)
        if session:
            session.is_used = True
            db.commit()

    @staticmethod
    def cleanup_expired(db: Session) -> int:
        """
        Elimina sesiones expiradas.

        Returns:
            Número de sesiones eliminadas
        """
        now = datetime.now(timezone.utc)
        count = db.query(PasswordResetSession).filter(
            PasswordResetSession.expires_at < now
        ).delete()
        db.commit()
        return count
