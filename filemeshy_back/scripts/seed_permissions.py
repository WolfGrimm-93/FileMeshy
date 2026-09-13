"""Siembra roles/permisos del sistema (SUPER_ADMIN/ADMIN/USER) a partir de
app/core/permissions.py -- fuente de verdad fija en código -- hacia las tablas
reales `permissions`/`roles`/`role_permissions` (fuente de verdad en runtime,
ver comentario en app/access_control/models.py::RolePermission).

SQL directo (Core), sin tocar el ORM a propósito: correr esto como script
standalone dispara el mismo bug de fondo que ya está documentado en
pendiente.md para cleanup_expired_sessions -- la resolución del mapper de
SQLAlchemy para relationship("User", ...) en Role es no determinística según
qué módulos ya se importaron en ESTE proceso puntual (funciona en la app real
porque app.main importa User explícitamente antes de que arranque nada).
Usar SQL crudo evita depender de que el grafo completo de mappers configure
bien en un proceso que no es la app real.

Idempotente: se puede correr las veces que haga falta (deploy nuevo, permiso
nuevo agregado al dict) sin duplicar ni pisar asignaciones manuales hechas
después desde la UI de Gestión de Permisos -- solo agrega lo que falta.

Uso:
    docker compose -f docker-compose.prod.yml exec backend python scripts/seed_permissions.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.permissions import CANONICAL_PERMISSIONS, ROLE_PERMISSIONS_CANONICAL
from app.shared.utils.uuid7 import uuid7

ROLE_DISPLAY_NAMES = {
    "SUPER_ADMIN": ("Super Administrador", "Acceso total al sistema, sin restricciones."),
    "ADMIN": ("Administrador", "Gestión completa de archivos, usuarios y configuración."),
    "USER": ("Usuario", "Uso básico: ver, subir y descargar sus propios archivos."),
}

# action -> permission_type (columna informativa, sin constraint en BD)
ACTION_TYPE = {
    "view": "read", "download": "read",
    "create": "create", "upload": "create",
    "delete": "delete", "revoke": "delete",
    "rename": "update", "move": "update", "edit": "update",
    "edit_email": "update", "edit_system": "update",
    "manage": "manage", "manage_roles": "manage",
}


def seed():
    db = SessionLocal()
    try:
        # 1. Roles del sistema
        role_ids = {}
        for name, (display_name, description) in ROLE_DISPLAY_NAMES.items():
            row = db.execute(text("SELECT id FROM roles WHERE name = :name"), {"name": name}).first()
            if row:
                role_ids[name] = row[0]
                continue
            new_id = uuid7()
            db.execute(
                text(
                    "INSERT INTO roles (id, name, display_name, description, is_system, is_active, permissions) "
                    "VALUES (:id, :name, :display_name, :description, true, true, '{}'::jsonb)"
                ),
                {"id": new_id, "name": name, "display_name": display_name, "description": description},
            )
            role_ids[name] = new_id
            print(f"[roles] creado: {name}")

        # 2. Catálogo de permisos
        perm_ids = {}
        for code, label in CANONICAL_PERMISSIONS.items():
            row = db.execute(
                text("SELECT id FROM permissions WHERE permission_code = :code"), {"code": code}
            ).first()
            if row:
                perm_ids[code] = row[0]
                continue
            resource, _, action = code.partition(".")
            new_id = uuid7()
            db.execute(
                text(
                    "INSERT INTO permissions "
                    "(id, permission_code, permission_name, permission_category, permission_type, resource, is_system) "
                    "VALUES (:id, :code, :label, :category, :ptype, :resource, true)"
                ),
                {
                    "id": new_id,
                    "code": code,
                    "label": label,
                    "category": resource,
                    "ptype": ACTION_TYPE.get(action, "manage"),
                    "resource": resource,
                },
            )
            perm_ids[code] = new_id
            print(f"[permissions] creado: {code}")

        # 3. Asignación rol <-> permiso
        for role_name, codes in ROLE_PERMISSIONS_CANONICAL.items():
            role_id = role_ids.get(role_name)
            if not role_id:
                continue
            existing = {
                r[0]
                for r in db.execute(
                    text("SELECT permission_id FROM role_permissions WHERE role_id = :role_id"),
                    {"role_id": role_id},
                ).all()
            }
            for code in codes:
                perm_id = perm_ids.get(code)
                if not perm_id or perm_id in existing:
                    continue
                db.execute(
                    text(
                        "INSERT INTO role_permissions (id, role_id, permission_id) "
                        "VALUES (:id, :role_id, :permission_id)"
                    ),
                    {"id": uuid7(), "role_id": role_id, "permission_id": perm_id},
                )
                print(f"[role_permissions] {role_name} -> {code}")

        db.commit()
        print("Seed de roles/permisos OK.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
