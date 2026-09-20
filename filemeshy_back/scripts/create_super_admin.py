"""Crea el primer usuario SUPER_ADMIN directo en la base, sin pasar por
/auth/register (deshabilitado a propósito de cara a internet -- alta de
usuarios se hace desde adentro, no público).

La lógica real vive en `create_super_admin()` -- reusable, la llama tanto
`main()` (uso manual por CLI, ver más abajo) como
`app/tenants/service.py::sembrar_cliente_nuevo` (alta de un tenant nuevo en
modo cloud, que necesita un super admin inicial para ese tenant).

Uso manual (CLI):
    La contraseña se lee de stdin (nunca de argv ni de una variable de entorno
    persistente) para no dejarla en el historial de shell ni en `ps` del host.

    printf '%s' 'la-contraseña' | \\
      docker compose -f docker-compose.prod.yml exec -T backend python scripts/create_super_admin.py <email>

SQL directo (Core), mismo criterio que scripts/seed_permissions.py -- evita
depender de que el grafo de mappers de SQLAlchemy configure bien en un
proceso standalone (ver ese script para el detalle del bug de fondo).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.shared.utils.uuid7 import uuid7


class SuperAdminCreationError(Exception):
    """Error de negocio al crear el super admin -- mensaje ya seguro para mostrar
    al llamante (CLI o `app.tenants.service.sembrar_cliente_nuevo`)."""


def create_super_admin(email: str, password: str, first_name: str = "Admin", last_name: str = "") -> dict:
    """Crea el primer usuario SUPER_ADMIN de la base actual (schema activo en
    `tenant_schema_ctx`, si aplica). No es un no-op silencioso si ya existe --
    devuelve `created=False` para que el llamante decida qué hacer.

    Devuelve {"user_id": str, "email": str, "created": bool}.
    Lanza `SuperAdminCreationError` si todavía no existe el rol SUPER_ADMIN
    (correr/sembrar roles y permisos primero -- ver scripts/seed_permissions.py).
    """
    db = SessionLocal()
    try:
        existing = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).first()
        if existing:
            return {"user_id": str(existing[0]), "email": email, "created": False}

        role = db.execute(text("SELECT id FROM roles WHERE name = 'SUPER_ADMIN'")).first()
        if not role:
            raise SuperAdminCreationError(
                "No existe el rol SUPER_ADMIN -- sembrar roles/permisos primero "
                "(scripts/seed_permissions.py)."
            )
        role_id = role[0]

        user_id = uuid7()
        hashed = get_password_hash(password)
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
                "first_name": first_name,
                "last_name": last_name,
                "role_id": role_id,
                "permissions": '["admin.manage"]',
            },
        )
        db.commit()
        return {"user_id": str(user_id), "email": email, "created": True}
    finally:
        db.close()


def main():
    if len(sys.argv) != 2:
        print("Uso: create_super_admin.py <email>", file=sys.stderr)
        sys.exit(1)
    email = sys.argv[1]

    password = sys.stdin.readline().rstrip("\n")
    if not password:
        print("ERROR: contraseña vacía (stdin)", file=sys.stderr)
        sys.exit(1)

    try:
        # Mismo nombre por defecto que la versión original de este script --
        # uso manual, siempre lo corre el mismo operador (wolfgrimm).
        resultado = create_super_admin(email, password, first_name="Wolf", last_name="Grimm")
    except SuperAdminCreationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if not resultado["created"]:
        print(f"Ya existe un usuario con email {email} -- no se crea de nuevo.")
        return
    print(f"Usuario SUPER_ADMIN creado: {email}")


if __name__ == "__main__":
    main()
