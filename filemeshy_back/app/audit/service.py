"""Servicio de auditoría: helpers manuales + middleware automático.

Fusiona, durante la migración a monolito modular:
- app/core/audit.py (log_audit, get_model_data -- helpers manuales)
- app/core/audit_middleware.py (AuditMiddleware -- auditoría automática de
  escritura, registrado en app/main.py)

Migrado tal cual, sin arreglar comportamiento (consigna explícita: es una
migración estructural, no una corrección de comportamiento) -- ver los dos
TODO marcados abajo, ya señalados en RECON_RIESGOS.md.
"""
import logging
from typing import Optional, Dict, Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from app.audit.repository import audit_log

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers manuales de auditoría (antes app/core/audit.py)
# ---------------------------------------------------------------------------

def log_audit(
    db,
    *,
    request: Optional[Request] = None,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    action: str,
    table_name: str,
    record_id: Any,
    old_data: Optional[Dict] = None,
    new_data: Optional[Dict] = None,
):
    """
    Helper para registrar acciones de auditoría.

    Usage:
        # En un endpoint después de crear un registro
        log_audit(
            db=db,
            request=request,
            user_id=current_user.id,
            user_email=current_user.email,
            action="CREATE",
            table_name="customer",
            record_id=new_customer.id,
            new_data={"name": new_customer.name, ...}
        )

    Args:
        db: Sesión de base de datos
        request: Request de FastAPI (opcional, para obtener IP y user_agent)
        user_id: ID del usuario
        user_email: Email del usuario
        action: CREATE, UPDATE, DELETE
        table_name: Nombre de la tabla
        record_id: ID del registro afectado
        old_data: Datos antes del cambio (para UPDATE/DELETE)
        new_data: Datos después del cambio (para CREATE/UPDATE)
    """
    try:
        # Extraer información del request si está disponible
        ip_address = None
        user_agent = None
        endpoint = None
        method = None

        if request:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")
            endpoint = str(request.url.path) if request.url else None
            method = request.method

        # Calcular cambios si hay old_data y new_data
        changes = None
        if old_data and new_data:
            changes = {}
            for key in new_data:
                if key in old_data and old_data[key] != new_data[key]:
                    changes[key] = {
                        "old": old_data[key],
                        "new": new_data[key]
                    }

        # Crear registro de auditoría
        audit_log.create_log(
            db=db,
            user_id=user_id,
            user_email=user_email,
            action=action,
            table_name=table_name,
            record_id=str(record_id),
            old_data=old_data,
            new_data=new_data,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
            endpoint=endpoint,
            method=method,
        )

        logger.info(f"Audit log created: {action} on {table_name}:{record_id} by {user_email}")

    except Exception as e:
        # No fallar la operación principal si falla la auditoría
        logger.error(f"Error creating audit log: {e}")


def get_model_data(model_instance, exclude_fields: list = None) -> Dict:
    """
    Convertir instancia de modelo SQLAlchemy a dict para auditoría.

    Args:
        model_instance: Instancia del modelo
        exclude_fields: Lista de campos a excluir (ej: ['password', 'hashed_password'])

    Returns:
        Dict con los datos del modelo
    """
    if not model_instance:
        return None

    exclude_fields = exclude_fields or []
    exclude_fields.extend(['_sa_instance_state', 'password', 'hashed_password'])

    data = {}
    for column in model_instance.__table__.columns:
        if column.name not in exclude_fields:
            value = getattr(model_instance, column.name)
            # Convertir tipos especiales a serializables
            if hasattr(value, 'isoformat'):  # datetime
                data[column.name] = value.isoformat() + 'Z'
            elif isinstance(value, (int, float, str, bool)) or value is None:
                data[column.name] = value
            else:
                data[column.name] = str(value)

    return data


# ---------------------------------------------------------------------------
# Middleware de auditoría automática (antes app/core/audit_middleware.py)
# ---------------------------------------------------------------------------
# Registra todas las operaciones de escritura (POST/PUT/PATCH/DELETE) en
# audit_log. Se ejecuta después de la respuesta para no afectar el tiempo de
# respuesta. Registrado en app/main.py (AuditMiddleware).

audit_mw_logger = logging.getLogger("filemeshy.audit")

# Métodos que se auditan
AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Acción genérica por método HTTP (fallback)
METHOD_ACTION = {
    "POST":   "CREATE",
    "PUT":    "UPDATE",
    "PATCH":  "UPDATE",
    "DELETE": "DELETE",
}

# Prefijos de rutas que NO se auditan
SKIP_PREFIXES = (
    "/api/v1/auth/",          # Auth tiene su propia auditoría
    "/api/v1/audit-logs",     # Evitar recursión
    "/api/v1/public/",        # Endpoints públicos sin usuario
    "/api/v1/notifications/", # Ruido de lectura/marcado
    "/health",
    "/favicon",
    "/docs",
    "/redoc",
    "/openapi",
)

# TODO: TABLE_NAME_MAP y SUFFIX_OVERRIDES todavía tienen restos de negocio
# no relacionado (payment-methods, tickets, support, external-services, stock,
# volume-prices) sin consumidor real hoy -- confirmado en RECON_RIESGOS.md.
# Migrado tal cual (migración estructural, no corrección de comportamiento);
# limpiarlos es una decisión de producto aparte.

# Segmentos de URL → nombre descriptivo en español
# Se quitaron las entradas de rutas de negocio no relacionado ya borradas
# (customers, products, suppliers, sales, invoices, cash-register-closes,
# warehouses, purchase-orders, inventory-*, document-types, unit-types,
# reports, product-extras, brands, categories, printing, geographic) -- ver
# poda equivalente de sus routers/endpoints.
TABLE_NAME_MAP = {
    "users":                  "users",  # unificado con el table_name="users" que ya usan los log_audit() explícitos de app/users/router.py -- antes quedaba "usuarios" acá (via AuditMiddleware) vs "users" allá para la misma acción de borrado
    "payment-methods":        "metodos_pago",
    "email-config":           "config_email",
    "system-config":          "config_sistema",
    "company":                "empresa",
    "roles":                  "roles",
    "tickets":                "tickets_soporte",
    "support":                "soporte",
    "admin":                  "administracion",
    "config":                 "configuracion",
    "preferences":            "preferencias",
    "external-services":      "servicios_externos",
}

# Rutas exactas → (action ≤10 chars, table_name, descripcion)
# Se quitaron los overrides de rutas de negocio ya borradas (cash-register-closes/open,
# sales/validate-discount-auth, products/refresh-stats).
EXACT_OVERRIDES: dict[str, tuple[str, str, str]] = {
    # Usuarios
    "/api/v1/users/me/change-password":                         ("UPDATE",     "contrasena",    "Cambio de contraseña desde perfil"),
    # Configuración empresa
    "/api/v1/admin/configuration/company/upload-logo":          ("UPLOAD",     "logo_empresa",  "Carga de logo de empresa"),
    "/api/v1/admin/configuration/company/upload-logo-icon":     ("UPLOAD",     "logo_empresa",  "Carga de ícono de empresa"),
    # Preferencias
    "/api/v1/user/preferences/my-preferences":                  ("UPDATE",     "preferencias",  "Actualización de preferencias del usuario"),
    # Email
    "/api/v1/admin/configuration/smtp/test":                    ("VERIFY",     "config_email",  "Prueba de configuración SMTP"),
}

# Sufijos de ruta → (action ≤10 chars, table_name_override o None, descripcion)
# Orden importa: más específico primero
SUFFIX_OVERRIDES: list[tuple[str, str, str | None, str]] = [
    ("/images/upload",         "UPLOAD",     "imagenes",    "Carga de imagen de producto"),
    ("/images/url",            "CREATE",     "imagenes",    "Imagen de producto desde URL"),
    ("/images/{id}/set-primary","UPDATE",    "imagenes",    "Imagen principal de producto actualizada"),
    ("/volume-prices",         "CREATE",     "precios",     "Creación de precios por volumen"),
    ("/deactivate",            "DEACTIVATE", None,          "Desactivación de registro"),
    ("/reactivate",            "ACTIVATE",   None,          "Reactivación de registro"),
    ("/activate",              "ACTIVATE",   None,          "Activación de registro"),
    ("/toggle",                "UPDATE",     None,          "Cambio de estado"),
    ("/void",                  "DELETE",     None,          "Anulación de registro"),
    ("/complete",              "UPDATE",     None,          "Cierre/completado de registro"),
    ("/payment",               "CREATE",     "pagos",       "Registro de pago"),
    ("/stock",                 "UPDATE",     None,          "Ajuste de stock"),
    ("/set-primary",           "UPDATE",     None,          "Imagen principal actualizada"),
    ("/adjust",                "UPDATE",     None,          "Ajuste de crédito/saldo"),
    ("/verify",                "VERIFY",     None,          "Verificación de registro"),
    ("/close",                 "UPDATE",     None,          "Cierre de cuadre de caja"),
    ("/status",                "UPDATE",     None,          "Cambio de estado"),
    ("/sessions",              "DELETE",     "sesiones",    "Cierre de sesiones de usuario"),
    ("/import",                "IMPORT",     None,          "Importación de datos"),
    ("/logo",                  "UPLOAD",     "logo",        "Carga de logo"),
    ("/upload-logo-icon",      "UPLOAD",     "logo",        "Carga de ícono"),
    ("/upload-logo",           "UPLOAD",     "logo",        "Carga de logo"),
    ("/check-permission",      "VERIFY",     "permisos",    "Verificación de permisos"),
    ("/refresh-stats",         "UPDATE",     None,          "Actualización de estadísticas"),
]


def _extract_table_and_id(path: str) -> tuple[str, str]:
    """
    Extrae el nombre descriptivo de la tabla y el record_id desde la URL.
    /api/v1/customers/5/deactivate → table=clientes, record_id=5
    /api/v1/customers              → table=clientes, record_id=new
    """
    parts = [p for p in path.strip("/").split("/") if p]
    # Remover prefijo api/v1
    if len(parts) >= 2 and parts[0] == "api" and parts[1] == "v1":
        parts = parts[2:]

    if not parts:
        return "unknown", "unknown"

    # Mapear el primer segmento a nombre descriptivo
    raw_table = parts[0]
    table = TABLE_NAME_MAP.get(raw_table, raw_table)

    # El segundo segmento es el ID si parece numérico o UUID
    non_id_segments = {
        "export", "import", "stats", "search", "health", "summary",
        "template", "open", "close", "verify", "toggle", "create",
        "upload-logo", "upload-logo-icon", "my-preferences",
        "change-password", "refresh-stats", "validate-discount-auth",
    }
    record_id = "new"
    if len(parts) > 1 and parts[1] not in non_id_segments:
        segment = parts[1]
        # Solo asignar como record_id si parece ID (numérico o UUID-like)
        if segment.isdigit() or (len(segment) > 8 and "-" in segment):
            record_id = segment

    return table, record_id


def _match_suffix(path: str) -> tuple[str, str | None, str] | None:
    """
    Busca el primer sufijo que coincida con el final de la ruta.
    Retorna (action, table_override, descripcion) o None.
    """
    for suffix, action, table_override, descripcion in SUFFIX_OVERRIDES:
        if path.endswith(suffix) or path.rstrip("/").endswith(suffix):
            return action, table_override, descripcion
    return None


def _get_user_from_token(authorization: str | None) -> tuple[str | None, str | None]:
    """Extrae user_id y user_email del JWT sin verificar firma (ya verificada por la ruta)."""
    if not authorization or not authorization.startswith("Bearer "):
        return None, None
    try:
        from app.core.security import decode_token
        token = authorization.split(" ", 1)[1]
        payload = decode_token(token)
        if payload:
            return str(payload.get("sub", "")), payload.get("email") or payload.get("sub")
        return None, None
    except Exception:
        return None, None


# TODO: AuditMiddleware no guarda tenant_id en el registro de audit_log --
# confirmado en RECON_RIESGOS.md. Migrado tal cual (migración estructural, no
# corrección de comportamiento); agregar tenant_id es una decisión de producto
# aparte, ligada al soporte multi-tenant (DEPLOYMENT_MODE=cloud).
class AuditMiddleware(BaseHTTPMiddleware):
    """Registra automáticamente todas las operaciones de escritura en audit_log."""

    async def dispatch(self, request: StarletteRequest, call_next) -> Response:
        response = await call_next(request)

        # Solo auditar métodos de escritura
        if request.method not in AUDIT_METHODS:
            return response

        # Saltar rutas excluidas
        path = request.url.path
        if any(path.startswith(prefix) for prefix in SKIP_PREFIXES):
            return response

        # Solo auditar operaciones exitosas (2xx)
        if not (200 <= response.status_code < 300):
            return response

        try:
            # Determinar action, table_name y descripcion
            descripcion: str | None = None

            # 1. Buscar coincidencia exacta
            if path in EXACT_OVERRIDES:
                action, table_name, descripcion = EXACT_OVERRIDES[path]
                _, record_id = _extract_table_and_id(path)

            # 2. Buscar coincidencia por sufijo
            elif suffix_match := _match_suffix(path):
                action, table_override, descripcion = suffix_match
                table_name, record_id = _extract_table_and_id(path)
                if table_override:
                    table_name = table_override

            # 3. Fallback genérico
            else:
                action = METHOD_ACTION.get(request.method, request.method[:10])
                table_name, record_id = _extract_table_and_id(path)

            user_id, user_email = _get_user_from_token(
                request.headers.get("authorization")
            )
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")

            # new_data con descripción legible si está disponible
            new_data = {"descripcion": descripcion} if descripcion else None

            from app.core.database import SessionLocal
            db = SessionLocal()
            try:
                audit_log.create_log(
                    db=db,
                    user_id=user_id,
                    user_email=user_email,
                    action=action,
                    table_name=table_name,
                    record_id=record_id,
                    new_data=new_data,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    endpoint=path,
                    method=request.method,
                )
            finally:
                db.close()

        except Exception as e:
            audit_mw_logger.error(f"Error en AuditMiddleware: {e}")

        return response
