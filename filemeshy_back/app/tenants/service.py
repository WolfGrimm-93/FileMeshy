"""Servicio de provisioning de tenants (Fase 3 - plataforma).

Logica reusable entre el script de CLI (scripts/instalacion/provisionar_tenant.py)
y los endpoints de /api/v1/platform/tenants -- ver Obsidian
"Desarrollo/Plataforma - Administracion de Tenants" para el diseño completo.

Secuencia atómica/reintentable:
  1. INSERT en `tenants` con is_active=false -- reserva slug/schema_name vía
     los UNIQUE constraints. Si hay conflicto, aborta sin tocar nada más.
  2. CREATE SCHEMA para el schema ya persistido y validado.
  3. Corre las migraciones de negocio contra ese schema (mecanismo de
     `-x schema=` de migrations/env.py).
  4. Siembra los datos base reusando, sin modificarlos, los 13 scripts de
     `scripts/instalacion/cliente_nuevo/` -- se cargan por ruta de archivo
     (sus nombres empiezan con dígito, no son importables como módulo
     normal) y se invoca su `main()` con `tenant_schema_ctx` ya seteado al
     schema del tenant.
  5. Solo si (2), (3) y (4) corrieron sin error: UPDATE tenants SET
     is_active = true. Activar al final (no apenas migran, ver auditoría
     2026-07-25) -- si la siembra falla a mitad de camino, el tenant NUNCA
     queda activo con roles/super_admin/security_policies incompletos.
  6. Si (2), (3) o (4) fallan: el tenant queda is_active=false -- el
     middleware de tenant ya lo bloquea con 403 automáticamente. No
     reintenta solo; el error incluye cómo limpiar a mano (excepto para
     schemas reservados, ver `mensaje_limpieza_manual`).
"""

import logging
import subprocess
import importlib.util
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import settings
from app.core.database import SessionLocal, engine, tenant_schema_ctx
from app.tenants.models import Tenant
from app.shared.utils.uuid7 import uuid7

logger = logging.getLogger(__name__)

FILEMESHY_BACK_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENTE_NUEVO_DIR = FILEMESHY_BACK_ROOT / "scripts" / "instalacion" / "cliente_nuevo"

# Mismo orden documentado en scripts/instalacion/cliente_nuevo/README.md.
# Varios scripts de siembra de modelos de negocio no relacionado (geografía,
# configuración de punto de venta, fidelización, tipos de unidad, almacenes)
# se quitaron: sembraban modelos podados en esta misma pasada.
CLIENTE_NUEVO_SCRIPTS = [
    "01_roles.py",
    "04_system_configuration.py",
    "07_security_policies.py",
    "08_company_settings.py",
    "09_super_admin.py",
    "10_payment_methods.py",
]

# Nombres de schema reservados/ya-existentes en cualquier base de Postgres.
# Canónico acá (no en app/schemas/platform.py, que lo importa de acá): esto
# protege operaciones reales de DDL, la validación del schema Pydantic es
# solo la primera línea de defensa. Encontrado por auditoría adversarial
# 2026-07-25: "public" pasa el CHECK constraint de formato de la tabla
# `tenants` sin problema (cumple la regex), y el mensaje de limpieza sugerido
# para un provisioning a medias (DROP SCHEMA ... CASCADE) destruiría el
# schema compartido por TODOS los tenants si no se bloquea explícitamente acá.
SCHEMA_NAMES_RESERVADOS = {"public", "pg_catalog", "information_schema", "pg_toast"}

# Límite generoso para "alembic upgrade head" contra un schema nuevo (47
# migraciones tardan 1-2s en la práctica) -- evita que un cuelgue real
# (deadlock de Postgres, red lenta) ocupe indefinidamente un hilo del
# threadpool compartido por TODA la API (encontrado por auditoría 2026-07-25:
# el endpoint es sync, corre en el threadpool de FastAPI/anyio junto con las
# ~260 rutas de negocio del resto del sistema).
MIGRACIONES_TIMEOUT_SEGUNDOS = 120


class ProvisioningError(Exception):
    """Error durante el provisioning de un tenant (mensaje seguro para mostrar al llamante)."""


def crear_fila_tenant(slug: str, schema_name: str, company_name: str, plan: str):
    """Inserta la fila y devuelve su id ya conocido de antemano (uuid7 generado en Python).

    Devuelve el UUID en vez del objeto ORM a propósito: `Session` expira los
    atributos tras `commit()` (expire_on_commit=True, el default), así que leer
    `tenant.id` después dispararía un SELECT implícito -- un round-trip extra
    innecesario, dado que el valor ya lo generamos nosotros mismos.
    """
    tenant_id = uuid7()
    db = SessionLocal()
    try:
        db.add(Tenant(
            id=tenant_id,
            slug=slug,
            schema_name=schema_name,
            company_name=company_name,
            plan=plan,
            is_active=False,
        ))
        db.commit()
        return tenant_id
    except IntegrityError as exc:
        db.rollback()
        # El detalle crudo de Postgres (exc.orig: nombre de constraint, DETAIL
        # con los valores de la fila) queda solo en el log del servidor -- no
        # se lo devolvemos al llamante HTTP (encontrado por auditoría 2026-07-25).
        logger.error(f"[Platform] IntegrityError creando tenant '{slug}'/'{schema_name}': {exc.orig}")
        raise ProvisioningError(
            f"El slug '{slug}' o el schema '{schema_name}' ya existen en `tenants`. "
            "Abortado antes de crear nada más."
        ) from exc
    finally:
        db.close()


def crear_schema_postgres(schema_name: str) -> None:
    quoted = engine.dialect.identifier_preparer.quote(schema_name)
    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA {quoted}"))
        conn.commit()


def correr_migraciones_de_negocio(schema_name: str) -> None:
    try:
        resultado = subprocess.run(
            ["alembic", "-x", f"schema={schema_name}", "upgrade", "head"],
            cwd=str(FILEMESHY_BACK_ROOT),
            capture_output=True,
            text=True,
            timeout=MIGRACIONES_TIMEOUT_SEGUNDOS,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error(f"[Platform] Timeout ({MIGRACIONES_TIMEOUT_SEGUNDOS}s) corriendo migraciones contra '{schema_name}'")
        raise ProvisioningError(
            f"Las migraciones de negocio no terminaron en {MIGRACIONES_TIMEOUT_SEGUNDOS}s contra "
            f"el schema '{schema_name}' -- puede seguir corriendo en el servidor, revisar a mano."
        ) from exc

    if resultado.returncode != 0:
        # stdout/stderr completos (pueden incluir tracebacks de Python y rutas
        # del servidor) quedan solo en el log -- no se los devolvemos al
        # llamante HTTP (encontrado por auditoría 2026-07-25).
        logger.error(
            f"[Platform] Migraciones fallaron contra '{schema_name}'.\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}"
        )
        raise ProvisioningError(
            f"Las migraciones de negocio fallaron contra el schema '{schema_name}' -- ver logs del servidor."
        )


def activar_tenant(tenant_id) -> None:
    db = SessionLocal()
    try:
        db.query(Tenant).filter(Tenant.id == tenant_id).update({"is_active": True})
        db.commit()
    finally:
        db.close()


def _cargar_script_por_ruta(path: Path):
    spec = importlib.util.spec_from_file_location(f"_seed_{path.stem}", path)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def sembrar_cliente_nuevo(schema_name: str) -> None:
    token = tenant_schema_ctx.set(schema_name)
    try:
        for filename in CLIENTE_NUEVO_SCRIPTS:
            path = CLIENTE_NUEVO_DIR / filename
            print(f"  -> {filename}")
            modulo = _cargar_script_por_ruta(path)
            modulo.main()
    finally:
        tenant_schema_ctx.reset(token)


def mensaje_limpieza_manual(slug: str, schema_name: str, tenant_id) -> str:
    if schema_name in SCHEMA_NAMES_RESERVADOS:
        # Defensa en profundidad: esto no debería ser alcanzable (el schema
        # Pydantic ya rechaza estos nombres), pero si algo cambia río arriba,
        # NUNCA sugerir un DROP SCHEMA sobre un schema compartido por todos
        # los tenants. Ver auditoría 2026-07-25.
        return (
            "\n"
            f"⚠️  El schema '{schema_name}' es RESERVADO/COMPARTIDO -- NO ejecutar "
            "DROP SCHEMA sobre él bajo ninguna circunstancia (destruiría datos de "
            "todos los tenants). Limpiar solo la fila huérfana a mano:\n\n"
            f"  DELETE FROM tenants WHERE id = '{tenant_id}';\n\n"
            "Y revisar por qué se intentó usar un nombre de schema reservado.\n"
        )
    return (
        "\n"
        f"El tenant '{slug}' (id={tenant_id}) quedó con is_active=false -- el "
        "middleware de tenant ya lo bloquea con 403 automáticamente, no hay riesgo "
        "de que se use a medias.\n"
        f"El schema '{schema_name}' puede haber quedado con tablas parcialmente creadas.\n"
        "No se reintenta solo. Para limpiar a mano y volver a intentar desde cero:\n\n"
        f"  DROP SCHEMA IF EXISTS {schema_name} CASCADE;\n"
        f"  DELETE FROM tenants WHERE id = '{tenant_id}';\n\n"
    )


def provisionar_tenant(slug: str, schema_name: str, company_name: str, plan: str = "standard") -> dict:
    """Ejecuta la secuencia completa de alta de un tenant.

    Devuelve {"tenant_id": str, "slug": str, "schema_name": str} si todo salió bien.
    Lanza ProvisioningError (mensaje seguro, con guía de limpieza si aplica) si algo falla.
    """
    if settings.DEPLOYMENT_MODE != "cloud":
        raise ProvisioningError(
            f"DEPLOYMENT_MODE actual es '{settings.DEPLOYMENT_MODE}'. Provisionar un tenant "
            "solo tiene sentido con DEPLOYMENT_MODE=cloud."
        )

    # Defensa en profundidad -- la validación real vive en el schema Pydantic
    # (TenantCreateRequest.rechazar_schema_reservado), pero esta función
    # también se llama desde el script de CLI, que no pasa por ahí.
    if schema_name in SCHEMA_NAMES_RESERVADOS or schema_name.startswith("pg_"):
        raise ProvisioningError(
            f"'{schema_name}' es un nombre de schema reservado/ya-existente en Postgres -- "
            "no se puede usar para un tenant."
        )

    print(f"1/4 Registrando tenant '{slug}' (schema '{schema_name}')...")
    tenant_id = crear_fila_tenant(slug, schema_name, company_name, plan)
    print(f"    OK -- id={tenant_id}, is_active=false (todavía)")

    print(f"2/4 Creando schema '{schema_name}'...")
    try:
        crear_schema_postgres(schema_name)
    except SQLAlchemyError as exc:
        logger.error(f"[Platform] Error creando schema '{schema_name}': {exc}")
        print(mensaje_limpieza_manual(slug, schema_name, tenant_id))
        raise ProvisioningError(f"No se pudo crear el schema '{schema_name}' -- ver logs del servidor.") from exc
    print("    OK")

    print("3/4 Corriendo migraciones de negocio contra el schema del tenant...")
    try:
        correr_migraciones_de_negocio(schema_name)
    except ProvisioningError as exc:
        print(f"    FALLÓ: {exc}")
        print(mensaje_limpieza_manual(slug, schema_name, tenant_id))
        raise
    print("    OK")

    print("4/4 Sembrando datos base (scripts/instalacion/cliente_nuevo/)...")
    try:
        sembrar_cliente_nuevo(schema_name)
    except Exception as exc:
        logger.error(f"[Platform] Error sembrando datos base en '{schema_name}': {exc}")
        print(mensaje_limpieza_manual(slug, schema_name, tenant_id))
        raise ProvisioningError(
            f"La siembra de datos base falló contra el schema '{schema_name}' -- ver logs del servidor."
        ) from exc

    # Activar al FINAL, no apenas migran -- si la siembra fallara a mitad de
    # camino, el tenant nunca queda activo con roles/super_admin incompletos
    # (encontrado por auditoría 2026-07-25).
    activar_tenant(tenant_id)
    print(f"OK -- tenant '{slug}' provisionado y activo.")

    return {"tenant_id": str(tenant_id), "slug": slug, "schema_name": schema_name}


# ============================================================
# WRAPPERS PÚBLICOS DE LECTURA
# ============================================================
# Para que platform/router.py deje de leer app.tenants.models.Tenant directo
# -- violación de fronteras señalada en la revisión adversarial
# (ADVERSARIAL_1_REPORTE.md, Hallazgo 1).

def list_tenants(db) -> list:
    """Lista todos los tenants, más recientes primero."""
    return db.query(Tenant).order_by(Tenant.created_at.desc()).all()


def get_tenant_by_id(db, tenant_id):
    """Tenant por ID, o None si no existe."""
    return db.query(Tenant).filter(Tenant.id == tenant_id).first()
