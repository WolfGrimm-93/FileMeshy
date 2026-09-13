"""CRUD operations for Audit Log."""

from sqlalchemy.orm import Session
from app.shared.repository_base import CRUDBase
from app.audit.models import AuditLog
from app.audit.schemas import AuditLogCreate, AuditLogFilters
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class CRUDAuditLog(CRUDBase[AuditLog, AuditLogCreate, None]):
    """
    CRUD optimizado para Audit Log.

    🚀 OPTIMIZADO PARA BIG DATA:
    - Filtros ordenados por selectividad (más restrictivos primero)
    - Búsqueda inteligente (≤3 chars prefijo, >3 completo)
    - ORDER BY created_at DESC (índice optimizado)
    """

    def create_log(
        self,
        db: Session,
        *,
        user_id: Optional[str],
        user_email: Optional[str],
        action: str,
        table_name: str,
        record_id: str,
        old_data: Optional[Dict[str, Any]] = None,
        new_data: Optional[Dict[str, Any]] = None,
        changes: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        endpoint: Optional[str] = None,
        method: Optional[str] = None,
    ) -> AuditLog:
        """
        Crear un registro de auditoría.

        Args:
            db: Sesión de base de datos
            user_id: ID del usuario
            user_email: Email del usuario
            action: CREATE, UPDATE, DELETE
            table_name: Nombre de la tabla
            record_id: ID del registro afectado
            old_data: Datos antes del cambio
            new_data: Datos después del cambio
            changes: Solo los campos que cambiaron
            ip_address: IP del usuario
            user_agent: User agent
            endpoint: Endpoint que ejecutó la acción
            method: Método HTTP

        Returns:
            AuditLog creado
        """
        try:
            audit_log = AuditLog(
                user_id=user_id,
                user_email=user_email,
                action=action,
                table_name=table_name,
                record_id=str(record_id),
                old_data=old_data,
                new_data=new_data,
                changes=changes,
                ip_address=ip_address,
                user_agent=user_agent,
                endpoint=endpoint,
                method=method,
            )
            db.add(audit_log)
            db.commit()
            db.refresh(audit_log)
            return audit_log
        except Exception as e:
            logger.error(f"Error creando audit log: {e}")
            db.rollback()
            raise

    def search(self, db: Session, filters: AuditLogFilters):
        """
        Búsqueda optimizada con filtros ordenados por selectividad.

        Orden de filtros (más selectivo primero):
        1. record_id (único)
        2. user_id (selectivo)
        3. table_name (categoría)
        4. action (categoría pequeña)
        5. start_date/end_date (rangos)
        6. search general (menos selectivo)
        """
        query = db.query(AuditLog)

        # 1. Filtro por record_id (muy selectivo)
        if filters.record_id:
            query = query.filter(AuditLog.record_id == filters.record_id)

        # 2. Filtro por user_id (selectivo)
        if filters.user_id:
            query = query.filter(AuditLog.user_id == filters.user_id)

        # 3. Filtro por tabla (categoría)
        if filters.table_name:
            query = query.filter(AuditLog.table_name == filters.table_name)

        # 4. Filtro por acción (categoría pequeña)
        if filters.action:
            query = query.filter(AuditLog.action == filters.action)

        # 5. Filtro por rango de fechas
        if filters.start_date:
            query = query.filter(AuditLog.created_at >= filters.start_date)

        if filters.end_date:
            query = query.filter(AuditLog.created_at <= filters.end_date)

        # 6. Búsqueda general (menos selectivo, al final)
        if filters.search:
            search_term = filters.search
            if len(search_term) <= 3:
                # Para búsquedas cortas: prefijo (más rápido)
                search_pattern = f"{search_term}%"
                query = query.filter(
                    (AuditLog.user_email.ilike(search_pattern)) |
                    (AuditLog.table_name.ilike(search_pattern)) |
                    (AuditLog.endpoint.ilike(search_pattern))
                )
            else:
                # Para búsquedas largas: búsqueda completa
                search_pattern = f"%{search_term}%"
                query = query.filter(
                    (AuditLog.user_email.ilike(search_pattern)) |
                    (AuditLog.table_name.ilike(search_pattern)) |
                    (AuditLog.record_id.ilike(search_pattern)) |
                    (AuditLog.endpoint.ilike(search_pattern))
                )

        # Ordenar por fecha descendente (más recientes primero)
        query = query.order_by(AuditLog.created_at.desc())

        return query.offset(filters.skip).limit(filters.limit).all()

    def count_search(self, db: Session, filters: AuditLogFilters) -> int:
        """Conteo con mismo ordenamiento que search()."""
        query = db.query(AuditLog)

        # Mismo orden de filtros que search()
        if filters.record_id:
            query = query.filter(AuditLog.record_id == filters.record_id)

        if filters.user_id:
            query = query.filter(AuditLog.user_id == filters.user_id)

        if filters.table_name:
            query = query.filter(AuditLog.table_name == filters.table_name)

        if filters.action:
            query = query.filter(AuditLog.action == filters.action)

        if filters.start_date:
            query = query.filter(AuditLog.created_at >= filters.start_date)

        if filters.end_date:
            query = query.filter(AuditLog.created_at <= filters.end_date)

        if filters.search:
            search_term = filters.search
            if len(search_term) <= 3:
                search_pattern = f"{search_term}%"
                query = query.filter(
                    (AuditLog.user_email.ilike(search_pattern)) |
                    (AuditLog.table_name.ilike(search_pattern)) |
                    (AuditLog.endpoint.ilike(search_pattern))
                )
            else:
                search_pattern = f"%{search_term}%"
                query = query.filter(
                    (AuditLog.user_email.ilike(search_pattern)) |
                    (AuditLog.table_name.ilike(search_pattern)) |
                    (AuditLog.record_id.ilike(search_pattern)) |
                    (AuditLog.endpoint.ilike(search_pattern))
                )

        return query.count()

    def get_by_table_and_record(
        self,
        db: Session,
        table_name: str,
        record_id: str,
        limit: int = 50
    ):
        """Obtener historial completo de un registro específico."""
        return db.query(AuditLog).filter(
            AuditLog.table_name == table_name,
            AuditLog.record_id == str(record_id)
        ).order_by(AuditLog.created_at.desc()).limit(limit).all()

    def get_user_activity(
        self,
        db: Session,
        user_id: str,
        limit: int = 100
    ):
        """Obtener actividad reciente de un usuario."""
        return db.query(AuditLog).filter(
            AuditLog.user_id == user_id
        ).order_by(AuditLog.created_at.desc()).limit(limit).all()


audit_log = CRUDAuditLog(AuditLog)
