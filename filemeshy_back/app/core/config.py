from pydantic_settings import BaseSettings
from typing import List, Literal, Optional


class Settings(BaseSettings):
    """Configuración principal de la aplicación."""
    
    # ===== APP SETTINGS =====
    PROJECT_NAME: str = "FileMeshy API"
    PROJECT_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # "development", "staging", "production"
    API_V1_PREFIX: str = "/api/v1"
    
    # ===== DATABASE =====
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/filemeshy"
    SQLALCHEMY_ECHO: bool = False
    
    # ===== REDIS CACHE =====
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_ENABLED: bool = True
    CACHE_TTL_STATS: int = 600  # 10 minutos para estadísticas
    CACHE_TTL_LIST: int = 300   # 5 minutos para listados

    # ===== CELERY WORKER =====
    # DB /1 para broker, DB /2 para resultados (DB /0 es la caché del API)
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    CELERY_WORKER_CONCURRENCY: int = 4
    
    # ===== JWT SETTINGS =====
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # ===== SERVER =====
    HOST: str = "0.0.0.0"
    PORT: int = 8888
    
    # ===== CORS =====
    # Tauri: 1420/1421 | Vite dev: 5173/5174 | Docker frontend: 47100
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:1420",
        "http://localhost:1421",
        "http://127.0.0.1:1420",
        "http://127.0.0.1:1421",
        "http://0.0.0.0:1420",
        "tauri://localhost",
        "https://tauri.localhost",
        "http://tauri.localhost",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://localhost:47100",
        "http://127.0.0.1:47100",
    ]

    # URL pública del frontend — usada en emails con enlaces de acción
    # Tauri dev: http://localhost:1420 | Docker: http://localhost:47100
    FRONTEND_URL: str = "http://localhost:1420"
    
    # ===== EMAIL (Optional) =====
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM: Optional[str] = None
    
    # ===== SECURITY SETTINGS =====
    # Rate limiting para password reset
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_MAX_ATTEMPTS: int = 5  # Máximo de intentos fallidos
    RATE_LIMIT_LOCK_DURATION: int = 900  # 15 minutos en segundos
    
    # Cookie security
    # None = auto-detectar (True en production, False en otros entornos)
    # Setear explícitamente en .env para sobreescribir (ej: COOKIE_SECURE=False en LAN sin HTTPS)
    COOKIE_SECURE: Optional[bool] = None
    COOKIE_SAMESITE: str = "strict"

    # ===== TENANT (Identificador de empresa para almacenamiento) =====
    # En modo cloud se setea por instalador. En modo local, "default" si no se setea.
    TENANT_SLUG: Optional[str] = None

    # ===== MULTI-TENANCY (Fase 2 - fundación) =====
    # "local": single-tenant, comportamiento actual (default, no negociable).
    # "cloud": multi-tenant, habilita TenantMiddleware y el search_path dinámico.
    DEPLOYMENT_MODE: Literal["local", "cloud"] = "local"

    # ===== PLATAFORMA (Fase 3 - alta y config de tenants) =====
    # Secreto compartido para el header X-Platform-Key -- solo se usa (y solo se
    # registra el router) en DEPLOYMENT_MODE=cloud. None en modo local: nadie
    # puede autenticarse contra estos endpoints porque ni siquiera existen.
    PLATFORM_API_KEY: Optional[str] = None

    # ===== MINIO (Almacenamiento de imágenes y archivos) =====
    MINIO_ENDPOINT: Optional[str] = None          # URL interna: http://minio:9000 (Docker) o http://localhost:9000 (local)
    MINIO_ACCESS_KEY: Optional[str] = None
    MINIO_SECRET_KEY: Optional[str] = None
    MINIO_BUCKET: str = "filemeshy-media"              # Bucket único — estructura: {company_code}/{modulo}/{id}/uuid.ext
    MINIO_PUBLIC_URL: Optional[str] = None        # URL pública para el navegador (ej: http://localhost:9000)
    MINIO_PRIVATE_BUCKET: str = "filemeshy-media-private"  # Bucket SIN política pública — PII (documentos de identidad), solo vía URL firmada

    # ===== FILES (Almacenamiento) =====
    MAX_UPLOAD_SIZE_MB: int = 100  # Nginx (filemeshy_front/nginx.conf) limita a 100MB -- nunca superar ese valor acá

    class Config:
        env_file = ".env"
        case_sensitive = True
    
    def __init__(self, **data):
        super().__init__(**data)
        # El valor por defecto de SECRET_KEY solo se permite en dev local --
        # antes solo se bloqueaba con ENVIRONMENT == "production" exacto, así
        # que "staging" (o cualquier typo/ambiente nuevo) se colaba con la
        # clave hardcodeada y pública en el repo. Criterio invertido: default
        # permitido únicamente si ENVIRONMENT es explícitamente dev/local.
        if self.ENVIRONMENT not in ("development", "local"):
            if self.SECRET_KEY == "your-super-secret-key-change-in-production":
                raise ValueError(
                    f"SECRET_KEY no puede ser el valor por defecto en ENVIRONMENT='{self.ENVIRONMENT}'. "
                    "Genera una clave segura: python -c \"import secrets; print(secrets.token_hex(32))\""
                )
        # Validación redundante (defensa en profundidad) - Literal ya lo valida en pydantic,
        # pero DEPLOYMENT_MODE controla registro condicional de middleware/listeners de seguridad.
        if self.DEPLOYMENT_MODE not in ("local", "cloud"):
            raise ValueError(
                f"DEPLOYMENT_MODE inválido: '{self.DEPLOYMENT_MODE}'. Valores permitidos: 'local' | 'cloud'."
            )
        # Auto-detectar solo si no fue seteado explícitamente en .env
        if self.COOKIE_SECURE is None:
            self.COOKIE_SECURE = (self.ENVIRONMENT == "production")


settings = Settings()
