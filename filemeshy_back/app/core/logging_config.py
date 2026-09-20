"""Configuración de logging para auditoría y debugging."""

import logging
import logging.handlers
from pathlib import Path

from app.core.config import settings

# Crear directorio de logs si no existe
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Configuración de logging
def setup_logging():
    """Configura el sistema de logging de la aplicación."""
    
    # Logger raíz
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # ===== AUDITORÍA: Logger especial para eventos de seguridad =====
    audit_logger = logging.getLogger("audit")
    audit_logger.setLevel(logging.INFO)
    
    # Handler: Auditoría a archivo (rotación diaria)
    audit_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOG_DIR / "audit.log",
        when="midnight",
        interval=1,
        backupCount=5  # Mantener 5 días de logs
    )
    audit_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    audit_logger.addHandler(audit_handler)
    
    # ===== APLICACIÓN: Logger de la app =====
    app_logger = logging.getLogger("app")
    # DEBUG solo en development/local -- en cualquier otro entorno, INFO.
    # Sin esto, app_logger quedaba SIEMPRE en DEBUG sin importar el entorno,
    # así que app_logger.debug(f"[DEV] Código para {email}: {code}")
    # (auth/router.py, fallback cuando falla el envío de email de reset de
    # contraseña) terminaba escribiendo el código de un solo uso en
    # logs/app.log en producción -- un código de reset de contraseña en
    # texto plano en disco (hallazgo de auditoría de seguridad). Con el
    # logger en INFO, ese `.debug(...)` ni se evalúa/escribe, sin tener que
    # tocar ese call site.
    app_logger.setLevel(
        logging.DEBUG if settings.ENVIRONMENT in ("development", "local") else logging.INFO
    )
    
    # Handler: Log de aplicación a archivo (rotación diaria)
    app_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOG_DIR / "app.log",
        when="midnight",
        interval=1,
        backupCount=5  # Mantener 5 días de logs
    )
    app_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    app_logger.addHandler(app_handler)
    
    # Handler: Consola para desarrollo
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S'
    ))
    
    app_logger.addHandler(console_handler)
    
    return audit_logger, app_logger


# Inicializar logging cuando se importa el módulo
audit_logger, app_logger = setup_logging()
