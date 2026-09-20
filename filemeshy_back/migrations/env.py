"""env.py"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool, text
from alembic import context
import os
import re
import sys

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.database import Base

# Import all models to register them with Base.metadata -- ya no existe un
# agregador `app.models`, cada módulo trae su propio models.py (ver
# RECON_RIESGOS.md, Riesgo #4: esto es tooling de infraestructura de Alembic,
# no un módulo de negocio importando de otro).
from app.auth.models import Session, PasswordResetSession
from app.users.models import User
from app.access_control.models import Role, Permission, RolePermission, UserPermissionOverride
from app.tenants.models import Tenant
from app.audit.models import AuditLog
from app.configuration.models import (
    SystemConfiguration, UserPreferences, SecurityPolicies,
)
from app.notifications.models import Notification
from app.files.models import Folder, File, Share, FileVersion
from app.storage_quota.models import UserStorageQuota
from app.tags.models import Tag, file_tags, folder_tags

# ===== CONFIGURATION =====
config = context.config

# Configurar la URL de base de datos
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Configurar logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ===== TARGET METADATA =====
target_metadata = Base.metadata

# ===== MULTI-SCHEMA (modo cloud) =====
# En modo local (default) nada de esto se ejecuta -- el comportamiento es
# idéntico al de siempre: single schema `public`, sin include_schemas ni
# version_table_schema. Esto es intencional y es el criterio de aceptación
# más importante del cambio: no romper instalaciones single-tenant existentes.
#
# En modo cloud hay dos flujos:
#   - Flujo "compartido" (sin -x schema): corre contra `public` con la tabla
#     `alembic_version` de siempre. Ahí vive la migración de la tabla `tenants`.
#   - Flujo "de negocio" (-x schema=nombre_tenant): corre las migraciones de
#     negocio (customers, sales, invoices, etc.) contra el schema del tenant,
#     con su propia tabla `alembic_version` DENTRO de ese schema
#     (`version_table_schema`), independiente de la de `public` y de la de
#     cualquier otro tenant.
#
# Nota: hoy toda la historia de migraciones es una sola cadena lineal (no hay
# ramas separadas "compartida" vs "de negocio"), así que correr el flujo de
# negocio contra un schema de tenant nuevo también aplica la migración de
# `tenants` dentro de ese schema (tabla que no se usa ahí, queda vacía). Separar
# esto en ramas de Alembic es trabajo futuro -- fuera de alcance de esta fase
# de fundación (ver instrucciones de la tarea: "sin reescribir todo Alembic").
SCHEMA_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,62}$")


def _get_target_schema() -> str | None:
    """Resuelve el schema de negocio destino en modo cloud (None = `public`).

    Se puede indicar por `-x schema=nombre_tenant` (patrón estándar de
    Alembic, ver `context.get_x_argument`) o por la variable de entorno
    `TARGET_SCHEMA` (útil cuando no es práctico pasar `-x`, ej. algunos
    orquestadores). Se valida con el mismo regex que el CHECK constraint de
    `tenants.schema_name` antes de usarlo en cualquier SQL crudo.
    """
    x_args = context.get_x_argument(as_dictionary=True)
    schema = x_args.get("schema") or os.environ.get("TARGET_SCHEMA")
    if not schema:
        return None
    schema = schema.strip()
    if not SCHEMA_NAME_RE.match(schema):
        raise ValueError(
            f"Nombre de schema inválido: '{schema}'. Debe cumplir {SCHEMA_NAME_RE.pattern!r}."
        )
    return schema


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    configure_kwargs = dict(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    if settings.DEPLOYMENT_MODE == "cloud":
        target_schema = _get_target_schema()
        if target_schema is not None:
            configure_kwargs["version_table_schema"] = target_schema
            configure_kwargs["include_schemas"] = True

    context.configure(**configure_kwargs)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    target_schema = None
    if settings.DEPLOYMENT_MODE == "cloud":
        target_schema = _get_target_schema()

    with connectable.connect() as connection:
        if target_schema is not None:
            # NullPool + sin listener de checkout (eso lo maneja app/core/database.py
            # para el pool de la app) -> hay que fijar el search_path a mano acá.
            #
            # OJO: este execute() dispara el autobegin de SQLAlchemy 2.0 (abre una
            # transacción en la conexión ANTES de context.configure()). Alembic lo
            # detecta como "_in_external_transaction" y por eso begin_transaction()
            # más abajo se vuelve un no-op (nullcontext) -- asume que el dueño de esa
            # transacción externa (este env.py) es quien va a comitear. Sin el
            # connection.commit() explícito de abajo, todo (incluida la tabla
            # alembic_version del schema del tenant) se pierde en silencio al cerrar
            # la conexión. Verificado con un repro mínimo contra Postgres real.
            # Cierra acá mismo la transacción "autobegin" que abrió el execute() de
            # arriba (SQLAlchemy 2.0 empieza una transacción en el primer execute()
            # de la conexión). Si no se cierra antes de context.configure(), Alembic
            # detecta una transacción externa en curso y begin_transaction() se
            # vuelve un no-op -- self._transaction nunca se setea, y autocommit_block()
            # (usado por las migraciones CONCURRENTLY, ver 0059) revienta con
            # "assert self._transaction is not None". El SET search_path es a nivel
            # de sesión (no SET LOCAL), sobrevive al commit sin problema. Ver
            # discusión oficial de Alembic #1150 (zzzeek) para el mismo patrón.
            quoted_schema = connection.dialect.identifier_preparer.quote(target_schema)
            connection.execute(text(f"SET search_path TO {quoted_schema}, public"))
            connection.commit()

        configure_kwargs = dict(connection=connection, target_metadata=target_metadata)
        if target_schema is not None:
            configure_kwargs["version_table_schema"] = target_schema
            configure_kwargs["include_schemas"] = True

        context.configure(**configure_kwargs)

        with context.begin_transaction():
            context.run_migrations()

        if target_schema is not None:
            connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
