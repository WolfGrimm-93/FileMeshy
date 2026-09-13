"""Crea el primer usuario SUPER_ADMIN directo en la base, sin pasar por
/auth/register (deshabilitado a propósito de cara a internet -- alta de
usuarios se hace desde adentro, no público).

La contraseña se lee de stdin (nunca de argv ni de una variable de entorno
persistente) para no dejarla en el historial de shell ni en `ps` del host.

SQL directo (Core), mismo criterio que scripts/seed_permissions.py -- evita
depender de que el grafo de mappers de SQLAlchemy configure bien en un
proceso standalone (ver ese script para el detalle del bug de fondo).

Uso:
    printf '%s' 'la-contraseña' | \
      docker compose -f docker-compose.prod.yml exec -T backend python scripts/create_super_admin.py <email>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.shared.utils.uuid7 import uuid7


def main():
    if len(sys.argv) != 2:
        print("Uso: create_super_admin.py <email>", file=sys.stderr)
        sys.exit(1)
    email = sys.argv[1]

    password = sys.stdin.readline().rstrip("\n")
    if not password:
        print("ERROR: contraseña vacía (stdin)", file=sys.stderr)
        sys.exit(1)

    hashed = get_password_hash(password)

    db = SessionLocal()
    try:
        existing = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).first()
        if existing:
            print(f"Ya existe un usuario con email {email} -- no se crea de nuevo.")
            return

        role = db.execute(text("SELECT id FROM roles WHERE name = 'SUPER_ADMIN'")).first()
        if not role:
            print("ERROR: no existe el rol SUPER_ADMIN -- correr scripts/seed_permissions.py primero", file=sys.stderr)
            sys.exit(1)
        role_id = role[0]

        user_id = uuid7()
        db.execute(
            text(
                "INSERT INTO users "
                "(id, email, hashed_password, first_name, last_name, role_id, permissions, is_active, is_superuser) "
                "VALUES (:id, :email, :hashed_password, :first_name, :last_name, :role_id, CAST(:permissions AS json), true, true)"
            ),
            {
                "id": user_id,
                "email": email,
                "hashed_password": hashed,
                "first_name": "Wolf",
                "last_name": "Grimm",
                "role_id": role_id,
                "permissions": '["admin.manage"]',
            },
        )
        db.commit()
        print(f"Usuario SUPER_ADMIN creado: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
