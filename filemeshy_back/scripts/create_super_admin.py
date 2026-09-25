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

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.shared.utils.uuid7 import uuid7


class SuperAdminCreationError(Exception):
    """Error de negocio al crear el super admin -- mensaje ya seguro para mostrar
    al llamante (CLI o `app.tenants.service.sembrar_cliente_nuevo`)."""


def _validate_email_or_raise(email: str) -> None:
    """Falla ACÁ, antes de insertar nada, si el email no pasaría el login --
    en vez de crear un SUPER_ADMIN que exista en la base pero nunca pueda
    entrar (Ronda 10, bug reportado: dominios como "empresa.local").

    Investigación de la causa real (no asumida, confirmada leyendo código
    en vivo dentro del contenedor):
      1. El LOGIN exige `EmailStr` (`app/users/schemas.py::LoginRequest`),
         pero este script inserta con SQL crudo, sin pasar por ningún
         schema -- puede crear un email que el login rechace.
      2. `EmailStr` de pydantic (2.5.2 en este proyecto) llama a
         `email_validator.validate_email(v, check_deliverability=False)`
         -- ese `False` está HARDCODEADO adentro de pydantic, no es una
         opción de este proyecto: NUNCA hace un lookup DNS real, ni para
         registro ni para login, hoy.
      3. Por eso ".local" NO se rechaza por deliverability (ya está
         apagado). Se rechaza por OTRO chequeo, distinto e INCONDICIONAL,
         de `email_validator` mismo: contra `SPECIAL_USE_DOMAIN_NAMES`
         (`arpa`, `invalid`, `local`, `localhost`, `onion`, `test` --
         confirmado en vivo imprimiendo la lista real de la versión
         instalada; OJO que ".example" NO está ahí pese a estar "reservado"
         por RFC 2606 -- esa RFC reserva los dominios puntuales
         example.com/.net/.org, no el sufijo ".example" en general, así que
         "cualquier-cosa.example" sí pasa esta librería). Ese chequeo corre
         SIEMPRE, no está gateado por `check_deliverability` ni por ningún
         otro parámetro que pydantic exponga (confirmado probando
         `globally_deliverable=False` y `test_environment=True` directo
         contra `email_validator`, ninguno lo evita).
      4. Conclusión: no hay ninguna forma de "relajar el deliverability
         check" para este caso puntual -- no es lo que está rechazando el
         email. La única forma real de arreglarlo sin tocar
         `LoginRequest`/`EmailStr` (fuera del alcance de este script) es
         no dejar crear la cuenta rota en primer lugar.

    Reutiliza `email_validator` directo (la misma librería que usa
    `EmailStr` por debajo) para que "lo que este script acepta" y "lo que
    el login acepta" sean EXACTAMENTE el mismo chequeo -- no una
    reimplementación que podría desincronizarse.
    """
    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError as exc:
        raise SuperAdminCreationError(
            f"Email inválido para login: {exc}. El login exige un email que "
            "pase la misma validación (ver app/users/schemas.py::LoginRequest, "
            "EmailStr) -- dominios especiales/reservados (.local, .test, "
            ".invalid, .localhost, .onion, .arpa) SIEMPRE se rechazan, no solo "
            "cuando no resuelven DNS real. Usá un dominio real (no hace falta "
            "que resuelva DNS de verdad, pero no puede ser uno de esos "
            "reservados)."
        ) from exc


def create_super_admin(email: str, password: str, first_name: str = "Admin", last_name: str = "") -> dict:
    """Crea el primer usuario SUPER_ADMIN de la base actual (schema activo en
    `tenant_schema_ctx`, si aplica). No es un no-op silencioso si ya existe --
    devuelve `created=False` para que el llamante decida qué hacer.

    Devuelve {"user_id": str, "email": str, "created": bool}.
    Lanza `SuperAdminCreationError` si todavía no existe el rol SUPER_ADMIN
    (correr/sembrar roles y permisos primero -- ver scripts/seed_permissions.py)
    o si el email no pasaría el login (ver `_validate_email_or_raise`).
    """
    _validate_email_or_raise(email)

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
