from contextvars import ContextVar

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import OperationalError
from app.core.config import settings
import logging
import time

# Configure logging
logger = logging.getLogger(__name__)

# ===== DATABASE ENGINE =====
# Configurar connect_args según el tipo de base de datos
connect_args = {}
if "sqlite" in settings.DATABASE_URL:
    connect_args["check_same_thread"] = False
elif "postgresql" in settings.DATABASE_URL:
    # Forzar UTF-8 en PostgreSQL para evitar problemas con caracteres especiales
    connect_args["client_encoding"] = "utf8"

_pool_kwargs = {}
if "sqlite" not in settings.DATABASE_URL:
    _pool_kwargs = {
        "pool_size": 10,          # Conexiones permanentes en el pool
        "max_overflow": 20,       # Conexiones adicionales bajo alta demanda
        "pool_recycle": 1800,     # Reciclar conexiones cada 30 min (evita stale)
        "pool_timeout": 30,       # Timeout para obtener conexión del pool
    }

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.SQLALCHEMY_ECHO,
    connect_args=connect_args,
    poolclass=StaticPool if "sqlite" in settings.DATABASE_URL else None,
    pool_pre_ping=True,  # Verificar conexiones antes de usarlas
    **_pool_kwargs,
)

# ===== TENANT SEARCH_PATH (solo modo cloud) =====
# Registro condicional en tiempo de arranque, igual que TenantMiddleware: en modo local
# estos listeners ni se registran (cero overhead en checkout/checkin del pool).
# A nivel de pool (no `SET LOCAL` en la sesión) porque el proyecto hace commits intermedios
# dentro de un mismo request y `SET LOCAL` muere al terminar cada transacción.
tenant_schema_ctx: ContextVar[str | None] = ContextVar("tenant_schema", default=None)

if settings.DEPLOYMENT_MODE == "cloud":

    @event.listens_for(engine, "checkout")
    def _set_tenant_search_path(dbapi_conn, connection_record, connection_proxy):
        schema = tenant_schema_ctx.get()
        target = schema if schema is not None else "public"
        quoted = engine.dialect.identifier_preparer.quote(target)
        cursor = dbapi_conn.cursor()
        cursor.execute(f"SET search_path TO {quoted}, public")
        cursor.close()
        # Commit explícito: psycopg2 abre transacción implícita en el primer statement.
        # Sin esto la conexión queda "idle in transaction" y pool_pre_ping (ya activo en
        # este proyecto) rompe en el próximo checkout ("set_session cannot be used inside
        # a transaction"), inutilizando la conexión.
        dbapi_conn.commit()

    @event.listens_for(engine, "checkin")
    def _reset_search_path_on_return(dbapi_conn, connection_record):
        # Fail-closed: la conexión SIEMPRE vuelve a public al soltarse, sin condicionar nada.
        cursor = dbapi_conn.cursor()
        cursor.execute("SET search_path TO public")
        cursor.close()
        dbapi_conn.commit()


# ===== SESSION FACTORY =====
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# ===== BASE MODEL =====
Base = declarative_base()


def get_db():
    """Dependency para obtener la sesión de base de datos."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection(max_retries: int = 5, retry_interval: int = 2) -> bool:
    """Verificar la conexión a la base de datos con reintentos.
    
    Args:
        max_retries: Número máximo de intentos
        retry_interval: Segundos entre intentos
        
    Returns:
        True si la conexión es exitosa, False en caso contrario
    """
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                logger.info("[DB] Database connection established")
                return True
        except OperationalError as e:
            if attempt < max_retries:
                logger.warning(
                    f"[DB] Attempt {attempt}/{max_retries} failed. "
                    f"Retrying in {retry_interval}s..."
                )
                time.sleep(retry_interval)
            else:
                logger.error(
                    f"[DB] Could not connect to database after {max_retries} attempts.\n"
                    f"Error: {str(e)}\n"
                    f"Note: Make sure PostgreSQL is running:\n"
                    f"   - Docker: cd filemeshy_back && docker-compose up -d postgres\n"
                    f"   - Local: Verify that PostgreSQL is active on port 5432"
                )
                return False
        except Exception as e:
            logger.error(f"[DB] Unexpected error connecting to database: {str(e)}")
            return False
    return False


