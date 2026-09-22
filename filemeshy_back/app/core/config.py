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

    # ===== SUBIDA MULTIPART DE ARCHIVOS GRANDES (Ronda 9) =====
    # Camino NUEVO y aparte del de arriba -- exclusivo para archivos por
    # encima de MAX_UPLOAD_SIZE_MB. El navegador sube cada parte DIRECTO a
    # MinIO (vía el proxy nginx público, ver PUBLIC_STORAGE_PROXY_URL más
    # abajo), los bytes nunca pasan por la memoria de este proceso -- ver
    # app/uploads/service.py.
    #
    # Techo del camino nuevo. 20GB es un valor de partida razonable (cubre
    # el caso real que motivó esta ronda, 10-15GB) sin comprometerse a un
    # límite mucho más alto sin necesidad real -- se puede subir por env sin
    # tocar código si hace falta.
    MAX_LARGE_UPLOAD_SIZE_MB: int = 20480
    # 256MB: con el techo de arriba da ~80 partes para el archivo más
    # grande admitido, bien lejos del límite de MinIO/S3 (5MB-5GB por
    # parte, hasta 10.000 partes) y de un tamaño cómodo para reintentar una
    # sola parte sin tener que resubir mucho si se corta la conexión.
    LARGE_UPLOAD_PART_SIZE_BYTES: int = 256 * 1024 * 1024
    # Tope GLOBAL de sesiones 'in_progress' SIMULTÁNEAS (todos los usuarios
    # sumados) -- protege el I/O de disco de MinIO de demasiadas subidas
    # grandes en paralelo, no la memoria del backend (que en este camino ya
    # no importa, ver docstring del módulo). Ver
    # app/uploads/service.py::_try_reserve_admission_slot.
    MAX_CONCURRENT_LARGE_UPLOADS: int = 15
    # Tope POR USUARIO -- agregado tras la revisión adversarial de seguridad
    # de esta ronda (hallazgo real, severidad ALTA, reproducido en vivo): sin
    # esto, un solo usuario podía abrir sesiones sin completarlas/abortarlas
    # hasta llenar el cupo GLOBAL de arriba y bloquear la feature para todos
    # los demás. 3 deja margen real (varios archivos grandes en simultáneo,
    # ej. subiendo distintos videos) sin que un usuario solo pueda acaparar
    # un cupo global de 15.
    MAX_CONCURRENT_LARGE_UPLOADS_PER_USER: int = 3
    # TTL del cupo de CONCURRENCIA activa en Redis -- deliberadamente CORTO
    # e independiente de `UPLOAD_SESSION_EXPIRY_HOURS` (48hs, el plazo para
    # RETOMAR una sesión vieja, ver más abajo). Son dos conceptos distintos
    # que NO deberían compartir plazo (mismo hallazgo de la revisión
    # adversarial): una sesión abandonada de verdad debe dejar de contar
    # contra el cupo de concurrencia mucho antes de que termine su ventana
    # de 48hs para reanudarse. Se renueva en cada
    # `POST /uploads/{id}/refresh-part-urls` mientras el usuario sigue
    # activo (ver `app/uploads/service.py::_renew_admission_lease`). 4h es
    # tiempo realista para subir hasta 20GB incluso en una conexión lenta.
    LARGE_UPLOAD_ADMISSION_LEASE_HOURS: int = 4
    # URL pública (la que el NAVEGADOR resuelve) del proxy nginx que
    # reenvía transparente hacia MinIO interno (http://minio:9000) -- las
    # URLs presignadas de cada parte se firman contra ESTE endpoint, nunca
    # contra MINIO_ENDPOINT (ver app/uploads/service.py::_get_presign_client
    # para el porqué completo, SigV4 firma el host).
    #
    # SOLO el host público, SIN ningún sufijo de path (nada de
    # "/storage-proxy" ni similar) -- corregido tras la verificación en vivo
    # de esta ronda: SigV4 firma también el PATH (CanonicalURI), no solo el
    # Host, así que un prefijo artificial en la URL nunca puede coincidir a
    # la vez con "lo que se firmó" y "el bucket real que MinIO necesita ver
    # en el path" (confirmado en vivo contra MinIO real probando las 3
    # combinaciones, ver hallazgo del agente de infra). El bucket
    # (`MINIO_PRIVATE_BUCKET`) queda como primer segmento del path gracias al
    # `addressing_style='path'` del cliente de firma -- la URL resultante
    # queda `{PUBLIC_STORAGE_PROXY_URL}/{bucket}/{key}?X-Amz-...`, exactamente
    # el mismo patrón de path que YA sirve hoy el location existente de
    # descarga en nginx.conf (`~ ^/(filemeshy-media|filemeshy-media-private)/`,
    # reusado también para subida por el agente de infra en vez de un
    # location nuevo dedicado). Construido/configurado por el agente de
    # infra de esta misma ronda (nginx.conf, docker-compose) -- acá solo se
    # declara el setting. Default de dev: puerto publicado del contenedor
    # `frontend` (58100, ver docker-compose.yml). Override real en
    # producción vía env (dominio público real del frontend).
    PUBLIC_STORAGE_PROXY_URL: str = "http://localhost:58100"
    # Plazo para RETOMAR una sesión de subida grande interrumpida (ej. se
    # cerró la pestaña, se reinició la PC) antes de que la tarea periódica
    # de limpieza (app/worker/tasks/uploads.py) la dé por abandonada, aborte
    # el multipart real en MinIO y libere la cuota reservada. 48h da margen
    # real (alguien puede tardar más de una noche en volver a una subida de
    # 15GB) sin dejar sesiones colgadas indefinidamente. Distinto del
    # vencimiento de cada URL presignada individual (mucho más corto, ver
    # `_PART_URL_EXPIRES_SECONDS` en app/uploads/service.py) -- para eso
    # está POST /uploads/{id}/refresh-part-urls.
    UPLOAD_SESSION_EXPIRY_HOURS: int = 48

    # ===== BACKUPS (Ronda 7 -- backups automáticos + verificación) =====
    # Backup de Postgres: pg_dump completo (toda la base física -- en modo
    # cloud eso incluye TODOS los schemas de tenant de una sola pasada,
    # porque son schemas de la MISMA base, no bases separadas), comprimido y
    # subido a MinIO (ver app/worker/tasks/backups.py::backup_postgres).
    # Bucket dedicado y PRIVADO (mismo criterio que MINIO_PRIVATE_BUCKET --
    # nunca política de lectura pública, ver
    # app/files/service.py::_ensure_private_bucket).
    BACKUP_POSTGRES_BUCKET: str = "filemeshy-backups"
    # Retención: después de cada backup exitoso, se borran (el objeto real
    # en MinIO -- la fila BackupRun se conserva como registro histórico) los
    # backups de Postgres con más de N días.
    BACKUP_RETENTION_DAYS: int = 14

    # ===== BACKUP DE MINIO A DESTINO S3 EXTERNO (Ronda 7, opcional) =====
    # Un backup de TODO el contenido de MinIO (filemeshy-media +
    # filemeshy-media-private) es caro (duplica el storage completo) y, si
    # se guarda en el MISMO disco/servidor, NO protege contra una falla de
    # disco real -- daría una falsa sensación de seguridad. Por eso el
    # backup de MinIO SOLO se intenta si estas 4 variables están TODAS
    # configuradas, apuntando a un S3-compatible EXTERNO real (otro
    # proveedor, otra región, otro servidor físico). Si falta cualquiera,
    # `backup_minio_objects` (app/worker/tasks/backups.py) se registra como
    # 'failed' con el motivo explícito, sin intentar nada -- limitación
    # conocida documentada en PENDIENTES.md, nunca una falsa sensación de
    # "ya hay backup de archivos".
    BACKUP_S3_ENDPOINT: Optional[str] = None
    BACKUP_S3_BUCKET: Optional[str] = None
    BACKUP_S3_ACCESS_KEY: Optional[str] = None
    BACKUP_S3_SECRET_KEY: Optional[str] = None

    # ===== OFFICE CONVERTER (Ronda 5 -- preview extendido) =====
    # URL interna (red Docker) del servicio aislado que convierte documentos
    # Office (docx/xlsx/pptx, + legacy doc/xls/ppt) a PDF para preview -- ver
    # `app/files/service.py::convert_office_to_pdf`. Contrato asumido:
    # POST {OFFICE_CONVERTER_URL}/convert (multipart, campo "file") -> bytes
    # de PDF, o 4xx/5xx con JSON {"detail": "..."}. Nunca alcanzable desde
    # el navegador (no tiene puerto publicado al host, igual que Postgres/
    # Redis/MinIO internos) -- el backend es el único cliente.
    OFFICE_CONVERTER_URL: str = "http://office_converter:8080"

    # ===== ANTIVIRUS (Ronda 7 -- escaneo de malware) =====
    # Host/puerto internos (red Docker) del servicio `clamd` -- ver
    # `app/files/service.py::scan_for_malware`. Mismo criterio que
    # OFFICE_CONVERTER_URL: nunca alcanzable desde el navegador (sin puerto
    # publicado al host, ver docker-compose.yml), solo el backend le habla
    # por nombre de servicio en la red interna de Docker.
    CLAMAV_HOST: str = "clamav"
    CLAMAV_PORT: int = 3310
    CLAMAV_SCAN_TIMEOUT_SECONDS: int = 30

    # ===== PROXIES DE CONFIANZA (ver app/auth/router.py::_get_real_ip) =====
    # Los headers CF-Connecting-IP/X-Real-IP los puede mandar CUALQUIER cliente
    # con el valor que quiera -- solo son confiables si la conexión TCP real
    # (request.client.host, no falsificable) viene de una IP en esta lista.
    # Vacío por defecto (secure-by-default): sin esto, rotar el header evadía
    # por completo el rate-limit/CAPTCHA por IP de /auth (hallazgo de
    # auditoría de seguridad, ver pendiente.md).
    # Producción: setear con la IP del contenedor frontend/nginx (el único
    # proxy real delante del backend, ver docker-compose.prod.yml) -- o
    # dejar vacío si Cloudflare Tunnel entrega directo sin un proxy
    # intermedio que reescriba esos headers.
    TRUSTED_PROXY_IPS: List[str] = []

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
