"""
Sistema de caché Redis para optimización de consultas.
Implementa estrategia híbrida: TTL + invalidación manual.
"""
import redis
import json
from decimal import Decimal
from typing import Optional, Any, Callable
from functools import wraps
import logging
from app.core.config import settings
from app.core.database import tenant_schema_ctx

logger = logging.getLogger(__name__)


def _json_default(obj):
    """Serializador de respaldo para json.dumps al cachear.

    Decimal se trata aparte de todo lo demas: dejarlo caer a str() (como antes)
    le hacia perder su naturaleza numerica en cada cache HIT -- un valor
    Numeric(14,4) volvia como "0.0000" en vez de 0, y comparaciones estrictas
    contra 0 en el frontend nunca se disparaban. Mismo criterio
    que fastapi.encoders.decimal_encoder para que lo que se relee de Redis siga
    siendo un numero real, no una respuesta que "se ve bien" al ojo pero rompe
    en runtime. Cualquier otro tipo sin serializador nativo sigue cayendo a
    str() como hasta ahora.
    """
    if isinstance(obj, Decimal):
        return int(obj) if obj.as_tuple().exponent >= 0 else float(obj)
    return str(obj)


def _scope_key(key: str) -> str:
    """Antepone el schema del tenant activo a la clave, solo en modo cloud.

    Sin esto, dos tenants pidiendo la misma clave (ej. "categories:list:1:50:None:None")
    comparten la misma entrada de Redis -- fuga de datos cross-tenant sin necesitar
    ningun token robado. En modo local (default) es no-op: tenant_schema_ctx nunca
    se setea porque TenantMiddleware ni se registra.
    """
    if settings.DEPLOYMENT_MODE == "cloud":
        schema = tenant_schema_ctx.get()
        if schema:
            return f"t:{schema}:{key}"
    return key


def _scope_pattern(pattern: str) -> str:
    """Mismo scoping que _scope_key, para delete_pattern (glob de Redis)."""
    return _scope_key(pattern)


class RedisCache:
    """Cliente Redis para caché de datos."""

    def __init__(self):
        """Inicializar conexión a Redis."""
        self.enabled = settings.REDIS_ENABLED
        self.client = None

        if self.enabled:
            try:
                self.client = redis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                # Verificar conexión
                self.client.ping()
                logger.info("Redis conectado exitosamente")
            except (redis.ConnectionError, redis.TimeoutError) as e:
                logger.warning(f"Redis no disponible: {e}. Cache desactivado.")
                self.enabled = False
                self.client = None

    def get(self, key: str) -> Optional[Any]:
        """
        Obtener valor de caché.

        Args:
            key: Clave del caché

        Returns:
            Valor deserializado o None si no existe
        """
        if not self.enabled or not self.client:
            return None

        key = _scope_key(key)
        try:
            value = self.client.get(key)
            if value:
                logger.debug(f"Cache HIT: {key}")
                return json.loads(value)
            logger.debug(f"Cache MISS: {key}")
            return None
        except Exception as e:
            logger.error(f"Error al obtener de caché {key}: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Guardar valor en caché con expiración.

        Args:
            key: Clave del caché
            value: Valor a cachear (será serializado a JSON)
            ttl: Tiempo de vida en segundos (default: 5 minutos)

        Returns:
            True si se guardó exitosamente
        """
        if not self.enabled or not self.client:
            return False

        key = _scope_key(key)
        try:
            serialized = json.dumps(value, default=_json_default)
            self.client.setex(key, ttl, serialized)
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Error al guardar en caché {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        Eliminar una clave de caché.

        Args:
            key: Clave a eliminar

        Returns:
            True si se eliminó
        """
        if not self.enabled or not self.client:
            return False

        key = _scope_key(key)
        try:
            self.client.delete(key)
            logger.debug(f"Cache DELETE: {key}")
            return True
        except Exception as e:
            logger.error(f"Error al eliminar de caché {key}: {e}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        """
        Eliminar todas las claves que coincidan con un patrón.

        Args:
            pattern: Patrón de búsqueda (ej: "customer_*")

        Returns:
            Número de claves eliminadas
        """
        if not self.enabled or not self.client:
            return 0

        pattern = _scope_pattern(pattern)
        try:
            keys = self.client.keys(pattern)
            if keys:
                deleted = self.client.delete(*keys)
                logger.debug(f"Cache DELETE PATTERN: {pattern} ({deleted} claves)")
                return deleted
            return 0
        except Exception as e:
            logger.error(f"Error al eliminar patrón {pattern}: {e}")
            return 0
    
    def clear_all(self) -> bool:
        """
        Limpiar todo el caché (usar con precaución).
        
        Returns:
            True si se limpió exitosamente
        """
        if not self.enabled or not self.client:
            return False
        
        try:
            self.client.flushdb()
            logger.warning("Cache completamente limpiado")
            return True
        except Exception as e:
            logger.error(f"Error al limpiar caché: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """
        Verificar si una clave existe en caché.
        
        Args:
            key: Clave a verificar
            
        Returns:
            True si existe
        """
        if not self.enabled or not self.client:
            return False

        key = _scope_key(key)
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            logger.error(f"Error al verificar existencia {key}: {e}")
            return False


# Instancia global de caché
cache = RedisCache()


def cached(key_prefix: str, ttl: Optional[int] = None):
    """
    Decorador para cachear resultados de funciones.
    
    Args:
        key_prefix: Prefijo de la clave de caché
        ttl: Tiempo de vida en segundos (usa default del settings si no se especifica)
        
    Example:
        @cached("customer_stats", ttl=600)
        def get_customer_stats(db: Session):
            # Esta función solo se ejecuta si no hay caché
            return expensive_query(db)
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generar clave única basada en argumentos
            cache_key = f"{key_prefix}"
            
            # Agregar parámetros a la clave si existen
            if kwargs:
                params = "_".join(f"{k}:{v}" for k, v in sorted(kwargs.items()) 
                                 if k not in ['db', 'current_user'])
                if params:
                    cache_key = f"{cache_key}:{params}"
            
            # Intentar obtener de caché
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Si no existe, ejecutar función
            result = func(*args, **kwargs)
            
            # Guardar en caché
            cache_ttl = ttl or settings.CACHE_TTL_LIST
            cache.set(cache_key, result, ttl=cache_ttl)
            
            return result
        
        return wrapper
    return decorator


# Funciones de utilidad para invalidación
def invalidate_users_cache():
    """Invalidar todo el caché relacionado con usuarios."""
    cache.delete_pattern("users:*")
    logger.info("Cache de usuarios invalidado")


def invalidate_reports_cache():
    """Invalidar todo el caché relacionado con reportes."""
    cache.delete_pattern("reports:*")
    logger.info("Cache de reportes invalidado")


def invalidate_configuration_cache():
    """Invalidar todo el caché relacionado con configuraciones."""
    cache.delete_pattern("config:*")
    logger.info("Cache de configuraciones invalidado")


def invalidate_stats_cache():
    """Invalidar caché de estadísticas."""
    cache.delete_pattern("*_stats")
    logger.info("Cache de estadisticas invalidado")


CONFIG_VERSION_KEY = "cfg_version:global"


def bump_config_version() -> None:
    """R5: incrementa la version global de configuracion.

    El frontend hace polling barato de esta version (GET /config/version) para
    enterarse de cambios de config hechos desde OTRA terminal/computadora -- el
    mecanismo viejo (evento `storage` de localStorage + `focus`) solo funciona
    entre pestañas del MISMO navegador, nunca entre maquinas distintas (el caso
    real de un negocio con varias cajas).

    Best-effort: si Redis no esta disponible, no debe romper el guardado de la
    config que lo llama (mismo criterio que el resto de invalidate_*_cache).
    """
    if not cache.enabled or not cache.client:
        return
    try:
        cache.client.incr(_scope_key(CONFIG_VERSION_KEY))
    except Exception as e:
        logger.error(f"Error al incrementar {CONFIG_VERSION_KEY}: {e}")


def get_config_version() -> int:
    """R5: version actual de config. 0 si Redis no esta disponible o aun no hubo
    ningun cambio -- el polling del frontend simplemente no dispara en ese caso.
    """
    if not cache.enabled or not cache.client:
        return 0
    try:
        val = cache.client.get(_scope_key(CONFIG_VERSION_KEY))
        return int(val) if val else 0
    except Exception as e:
        logger.error(f"Error al leer {CONFIG_VERSION_KEY}: {e}")
        return 0


def invalidate_permissions_cache():
    """Invalidar caché del catálogo de permisos.

    Debe llamarse cada vez que se crea, edita o elimina un registro en
    la tabla `permissions`, para que el próximo GET /permissions/available
    refleje los cambios desde la BD en lugar de devolver datos obsoletos.
    """
    cache.delete("permissions:available")
    logger.info("Cache de permisos invalidado")


# ── Módulos de negocio activables/desactivables ─────────────────────────────
# Flags booleanos en system_configuration que gatean el acceso a routers
# completos vía app.api.deps.require_module. TTL corto: al desactivar un
# módulo, invalidate_module_flag_cache lo saca de inmediato, pero igual
# conviene que expire solo por si la invalidación falla.
MODULE_FLAG_CACHE_PREFIX = "module_flag:"
MODULE_FLAG_CACHE_TTL = 60


def get_module_flag_cache_key(module_key: str) -> str:
    return f"{MODULE_FLAG_CACHE_PREFIX}{module_key}"


def invalidate_module_flag_cache(module_key: str) -> None:
    """Invalidar el flag cacheado de un módulo (llamar tras actualizar su valor)."""
    cache.delete(get_module_flag_cache_key(module_key))
    logger.info(f"Cache de modulo invalidado: {module_key}")
