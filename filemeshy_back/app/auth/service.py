"""
Servicio de auth: autenticación (login/refresh), gestión de sesiones, reset de
contraseña (hash de código + JWT de reset), 2FA (TOTP), rate limiting de
login/reset, y las dependencias FastAPI de "usuario actual" (extraídas de
app/api/deps.py durante la migración a monolito modular: get_current_user,
get_current_active_user, get_current_superuser, invalidate_session_active_cache,
y el cache de sesión/usuario autenticado en memoria/Redis).

También incluye AuditService (antes app/services/audit_service.py): sus 4
métodos son eventos de seguridad de password/login que solo se llaman desde
auth/router.py (9 call sites) y users/router.py (1 call site) -- no escriben a
la tabla `audit_log` (esa es responsabilidad de audit/service.py, un mecanismo
distinto), por eso quedan acá y no en `audit`.
"""

import base64
import hashlib
import hmac
import io
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple, Union
from uuid import UUID

import pyotp
import qrcode
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt  # PyJWT (Ronda 10: migrado desde python-jose, sin mantenimiento activo)
from passlib.context import CryptContext
from sqlalchemy.orm import Session, joinedload

from app.core.cache import cache
from app.core.config import settings
from app.core.database import get_db, tenant_schema_ctx
from app.core.logging_config import app_logger
from app.core.security import (
    create_access_token,
    create_pre_auth_token,
    create_refresh_token,
    decode_token,
)
from app.access_control.service import permission_mapper
from app.auth.models import Session as SessionModel
from app.users.models import User
from app.users.service import user_service
from app.users.schemas import (
    TokenResponse,
    TwoFactorLoginResponse,
    User as UserSchema,
)

# ============================================================
# DEPENDENCIA DE SEGURIDAD (extraída de app/api/deps.py)
# ============================================================
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")


# ============================================================
# CACHE DE AUTENTICACIÓN EN MEMORIA (extraída de app/api/deps.py)
# ============================================================
# Evita consultar la DB por cada request del mismo usuario.
# TTL de 60 segundos, máximo 100 entradas.
_auth_cache: dict[str, tuple[float, int]] = {}  # token_hash → (expiry, user_id)
_auth_cache_lock = threading.Lock()
_AUTH_CACHE_TTL = 60  # segundos
_AUTH_CACHE_MAX = 100


def _get_cached_user_id(token: str) -> int | None:
    """Obtener user_id cacheado por token (sin hit a DB)."""
    key = hash(token)
    with _auth_cache_lock:
        entry = _auth_cache.get(key)
        if entry and entry[0] > time.time():
            return entry[1]
        if entry:
            del _auth_cache[key]
    return None


def _set_cached_user_id(token: str, user_id: int) -> None:
    """Cachear user_id por token."""
    key = hash(token)
    with _auth_cache_lock:
        if len(_auth_cache) >= _AUTH_CACHE_MAX:
            # Limpiar entradas expiradas
            now = time.time()
            expired = [k for k, v in _auth_cache.items() if v[0] <= now]
            for k in expired:
                del _auth_cache[k]
        _auth_cache[key] = (time.time() + _AUTH_CACHE_TTL, user_id)


def invalidate_auth_cache() -> None:
    """Invalidar todo el cache de auth (llamar al cambiar permisos/roles)."""
    with _auth_cache_lock:
        _auth_cache.clear()


# ============================================================
# CACHE DE SESIÓN ACTIVA (extraída de app/api/deps.py)
# ============================================================
# El JWT en sí sigue siendo criptográficamente válido hasta que expira, sin
# importar logout/revocación -- por eso get_current_user necesita chequear
# contra la Session real (Session.is_active). Cacheado en Redis (mismo cliente
# `cache` que usa RateLimiter más abajo) con TTL corto, en vez de un dict en
# memoria de proceso: con más de un worker/réplica de uvicorn corriendo, un
# dict local solo ve la invalidación en el worker que atendió el logout --
# los demás siguen aceptando el access token viejo hasta que expira. Redis es
# compartido entre todos, así que la revocación es real sin importar cuántos
# procesos corran. Si Redis no está disponible, cache.get/set son no-ops (ver
# RedisCache): cada request cae directo a la consulta a la Session en DB, sin
# fallback en memoria -- más lento, pero nunca deja pasar una sesión revocada.
_SESSION_ACTIVE_CACHE_TTL = 30  # segundos


def _session_active_cache_key(jti: str) -> str:
    return f"session_active:{jti}"


def invalidate_session_active_cache(jti: str) -> None:
    """Invalida el estado cacheado (en Redis) de una sesión puntual por su
    JTI de access token. Llamar apenas se marca Session.is_active = False
    (logout, revoke_user_session, revoke_all_user_sessions) para que el 401
    llegue antes de _SESSION_ACTIVE_CACHE_TTL segundos en vez de esperarlo --
    no es instantáneo en el sentido estricto (best-effort: si Redis está caído,
    cache.delete es un no-op), pero como no hay fallback en memoria en ese
    caso, cada request ya está consultando la DB directo de todas formas."""
    if not jti:
        return
    cache.delete(_session_active_cache_key(jti))


def _is_session_jti_active(jti: str, db: Session) -> bool:
    """Verifica que exista una Session activa para este JTI de access token."""
    cache_key = _session_active_cache_key(jti)
    cached = cache.get(cache_key)
    if cached is not None:
        return bool(cached)

    session = db.query(SessionModel).filter(SessionModel.access_token_jti == jti).first()
    is_active = bool(session and session.is_active)

    cache.set(cache_key, is_active, ttl=_SESSION_ACTIVE_CACHE_TTL)

    return is_active


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """Obtiene el usuario actual del token JWT con cache en memoria."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception

    email: str = payload.get("sub")
    if email is None:
        raise credentials_exception

    # El token queda atado al tenant donde se emitió (ver AuthService.login) -- sin
    # esto, el mismo token reenviado con el header X-Tenant-Slug de OTRO tenant
    # autenticaría como el usuario con ese email en ese otro schema.
    if settings.DEPLOYMENT_MODE == "cloud" and payload.get("tenant") != tenant_schema_ctx.get():
        raise credentials_exception

    # La sesión debe seguir activa -- si el usuario hizo logout o un admin
    # revocó esta sesión, el JWT sigue siendo válido hasta que expira pero ya
    # no debe autenticar nada (ver Session.is_active / _close_session_cookie).
    jti = payload.get("jti")
    if not jti or not _is_session_jti_active(jti, db):
        raise credentials_exception

    # Intentar obtener user_id del cache en memoria
    cached_user_id = _get_cached_user_id(token)
    if cached_user_id is not None:
        user = db.query(User).options(joinedload(User.role_obj)).get(cached_user_id)
        if user and user.email == email:
            return user

    # Cache miss: buscar por email
    user = db.query(User).options(joinedload(User.role_obj)).filter(User.email == email).first()
    if user is None:
        raise credentials_exception

    # Guardar en cache
    _set_cached_user_id(token, user.id)

    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Obtiene el usuario actual y verifica que esté activo."""
    if not user_service.is_active(current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario inactivo"
        )
    return current_user


async def get_current_superuser(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Obtiene el usuario actual y verifica que tenga el rol SUPER_ADMIN."""
    if not (current_user.role_obj and current_user.role_obj.name == 'SUPER_ADMIN'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos suficientes"
        )
    return current_user


# ============================================================
# AUTENTICACIÓN (antes app/services/auth_service.py)
# ============================================================

class AuthService:
    """Servicio de autenticación."""

    @staticmethod
    def login(
        db: Session,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Union[TokenResponse, TwoFactorLoginResponse]:
        """Autentica un usuario. Si tiene 2FA activo retorna pre_auth_token en lugar de tokens completos."""
        # Verificar si el usuario existe
        user = user_service.authenticate(db, email=email, password=password)
        if not user:
            raise ValueError("Email o contraseña incorrectos")

        # Verificar si el usuario está activo
        if not user.is_active:
            raise ValueError("Tu cuenta ha sido desactivada. Contacta al administrador")

        # Si el usuario tiene 2FA habilitado, pausar el login aquí para pedir el TOTP.
        if getattr(user, 'totp_enabled', False):
            pre_auth_token = create_pre_auth_token(user.email)
            return TwoFactorLoginResponse(
                requires_2fa=True,
                pre_auth_token=pre_auth_token
            )

        # Actualizar último login
        user.last_login = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)

        # ✅ INVALIDAR SESIONES ANTERIORES DEL MISMO DISPOSITIVO
        # Permite múltiples sesiones (PC, móvil, tablet) pero una por dispositivo
        if user_agent:
            db.query(SessionModel).filter(
                SessionModel.user_id == user.id,
                SessionModel.user_agent == user_agent,
                SessionModel.is_active == True
            ).update({"is_active": False})
            db.commit()

        # Normalizar permisos al formato canónico
        user.permissions = permission_mapper.normalize_permissions(user.permissions, db=db)

        # Crear tokens con JTI
        access_token_expires = timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        access_token, access_jti = create_access_token(
            data={"sub": user.email, "tenant": tenant_schema_ctx.get()},
            expires_delta=access_token_expires
        )
        refresh_token, refresh_jti = create_refresh_token(data={"sub": user.email, "tenant": tenant_schema_ctx.get()})

        # Registrar sesión en la base de datos
        refresh_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        session = SessionModel(
            user_id=user.id,
            access_token_jti=access_jti,
            refresh_token_jti=refresh_jti,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=refresh_expires_at,
            is_active=True
        )
        db.add(session)
        db.commit()

        # Obtener preferencias del usuario para incluir el tema
        # user_id se convierte a string porque UserPreferences.user_id es String
        from app.configuration.service import get_user_preferences
        user_prefs = get_user_preferences(db, str(user.id))

        # Convertir usuario a schema y agregar tema
        user_schema = UserSchema.model_validate(user)

        # Llenar el campo role desde la relación role_obj
        if user.role_obj:
            user_schema.role = user.role_obj.name

        if user_prefs:
            user_schema.theme = user_prefs.theme
        else:
            # Si no existen preferencias, usar tema por defecto
            user_schema.theme = "auto"

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_schema
        )

    @staticmethod
    def complete_login_after_2fa(
        db: Session,
        email: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> TokenResponse:
        """Completa el login después de verificar el código 2FA. Genera tokens completos."""
        user = user_service.get_by_email(db, email=email)
        if not user or not user.is_active:
            raise ValueError("Usuario no encontrado o inactivo")

        user.last_login = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)

        if user_agent:
            db.query(SessionModel).filter(
                SessionModel.user_id == user.id,
                SessionModel.user_agent == user_agent,
                SessionModel.is_active == True
            ).update({"is_active": False})
            db.commit()

        user.permissions = permission_mapper.normalize_permissions(user.permissions, db=db)

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token, access_jti = create_access_token(
            data={"sub": user.email, "tenant": tenant_schema_ctx.get()},
            expires_delta=access_token_expires
        )
        refresh_token, refresh_jti = create_refresh_token(data={"sub": user.email, "tenant": tenant_schema_ctx.get()})

        refresh_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        session = SessionModel(
            user_id=user.id,
            access_token_jti=access_jti,
            refresh_token_jti=refresh_jti,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=refresh_expires_at,
            is_active=True
        )
        db.add(session)
        db.commit()

        from app.configuration.service import get_user_preferences
        user_prefs = get_user_preferences(db, str(user.id))
        user_schema = UserSchema.model_validate(user)
        if user.role_obj:
            user_schema.role = user.role_obj.name
        if user_prefs:
            user_schema.theme = user_prefs.theme
        else:
            user_schema.theme = "auto"

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_schema
        )

    @staticmethod
    def refresh_access_token(db: Session, refresh_token: str) -> Tuple[str, str]:
        """Refresh access token and rotate refresh token.

        Returns:
            Tuple[str, str]: (new_access_token, new_refresh_token)
        """
        # Cleanup expired sessions
        db.query(SessionModel).filter(
            SessionModel.expires_at < datetime.now(timezone.utc),
            SessionModel.is_active == True
        ).update({"is_active": False})
        db.commit()

        payload = decode_token(refresh_token)
        if payload is None or payload.get("type") != "refresh":
            raise ValueError("Token de refresco inválido")

        # El refresh token quedó atado al tenant donde se emitió (ver login()) --
        # un token de otro tenant no puede usarse para renovar acceso acá, ni
        # siquiera reusando el mismo email/usuario.
        if settings.DEPLOYMENT_MODE == "cloud" and payload.get("tenant") != tenant_schema_ctx.get():
            raise ValueError("Token de refresco inválido")

        refresh_jti = payload.get("jti")
        if not refresh_jti:
            raise ValueError("Token sin JTI inválido")

        session = db.query(SessionModel).filter(
            SessionModel.refresh_token_jti == refresh_jti,
            SessionModel.is_active == True
        ).first()

        if not session:
            raise ValueError("Sesión inválida o expirada")

        email = payload.get("sub")
        user = user_service.get_by_email(db, email=email)
        if not user:
            raise ValueError("Usuario no encontrado")

        user.last_login = datetime.now(timezone.utc)
        session.last_activity = datetime.now(timezone.utc)

        # New access token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token, new_access_jti = create_access_token(
            data={"sub": user.email, "tenant": payload.get("tenant")},
            expires_delta=access_token_expires
        )

        # Rotate refresh token
        new_refresh_token, new_refresh_jti = create_refresh_token(data={"sub": user.email, "tenant": payload.get("tenant")})
        new_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        session.access_token_jti = new_access_jti
        session.refresh_token_jti = new_refresh_jti
        session.expires_at = new_expires_at

        db.commit()

        return access_token, new_refresh_token


# ============================================================
# GESTIÓN DE SESIONES (antes app/services/session_service.py)
# ============================================================

class SessionService:
    """Servicio para gestión de sesiones."""

    @staticmethod
    def cleanup_expired_sessions(db: Session) -> int:
        """
        Elimina sesiones expiradas de la base de datos.

        Args:
            db: Sesión de base de datos

        Returns:
            int: Número de sesiones eliminadas
        """
        try:
            # Buscar sesiones expiradas (expires_at < ahora)
            expired_sessions = db.query(SessionModel).filter(
                SessionModel.expires_at < datetime.now(timezone.utc)
            ).all()

            count = len(expired_sessions)

            # Eliminar sesiones expiradas
            for session in expired_sessions:
                db.delete(session)

            db.commit()

            if count > 0:
                app_logger.info(f"Limpieza de sesiones: {count} sesiones expiradas eliminadas")

            return count

        except Exception as e:
            db.rollback()
            app_logger.error(f"Error limpiando sesiones expiradas: {str(e)}")
            raise

    @staticmethod
    def deactivate_expired_sessions(db: Session) -> int:
        """
        Desactiva sesiones expiradas sin eliminarlas (para auditoría).

        Args:
            db: Sesión de base de datos

        Returns:
            int: Número de sesiones desactivadas
        """
        try:
            # Buscar sesiones activas expiradas
            expired_sessions = db.query(SessionModel).filter(
                SessionModel.is_active == True,
                SessionModel.expires_at < datetime.now(timezone.utc)
            ).all()

            count = len(expired_sessions)

            # Desactivar sesiones
            for session in expired_sessions:
                session.is_active = False

            db.commit()

            if count > 0:
                app_logger.info(f"Limpieza de sesiones: {count} sesiones expiradas desactivadas")

            return count

        except Exception as e:
            db.rollback()
            app_logger.error(f"Error desactivando sesiones expiradas: {str(e)}")
            raise

    @staticmethod
    def get_user_sessions(db: Session, user_id: UUID, include_expired: bool = False):
        """
        Obtiene todas las sesiones de un usuario.

        Args:
            db: Sesión de base de datos
            user_id: ID del usuario
            include_expired: Si incluir sesiones expiradas

        Returns:
            List[SessionModel]: Lista de sesiones
        """
        query = db.query(SessionModel).filter(SessionModel.user_id == user_id)

        if not include_expired:
            query = query.filter(
                SessionModel.is_active == True,
                SessionModel.expires_at > datetime.now(timezone.utc)
            )

        return query.order_by(SessionModel.created_at.desc()).all()

    @staticmethod
    def revoke_user_sessions(db: Session, user_id: UUID) -> int:
        """
        Revoca todas las sesiones activas de un usuario.
        Útil cuando se cambia la contraseña o se desactiva un usuario.

        Args:
            db: Sesión de base de datos
            user_id: ID del usuario

        Returns:
            int: Número de sesiones revocadas
        """
        try:
            sessions = db.query(SessionModel).filter(
                SessionModel.user_id == user_id,
                SessionModel.is_active == True
            ).all()

            count = len(sessions)

            for session in sessions:
                session.is_active = False

            db.commit()

            app_logger.info(f"Se revocaron {count} sesiones del usuario {user_id}")

            return count

        except Exception as e:
            db.rollback()
            app_logger.error(f"Error revocando sesiones del usuario {user_id}: {str(e)}")
            raise


# ============================================================
# JWT PARA RESET DE CONTRASEÑA (antes app/services/jwt_reset_service.py)
# ============================================================
# Genera y valida reset_token con scope password_reset. TTL corto (5-10 min)
# y uso único. Usa PyJWT (igual que AuthService de acá arriba -- Ronda 10:
# migrado desde python-jose).

class JWTResetService:
    """Manejo de JWT para password reset."""

    # TTL del reset_token: 5 minutos
    RESET_TOKEN_EXPIRY_MINUTES = 5

    # Scope del token
    RESET_SCOPE = "password_reset"

    @staticmethod
    def generate_reset_token(
        user_id: UUID,
        session_id: str,
        email: str
    ) -> str:
        """
        Genera JWT reset_token.

        Args:
            user_id: ID del usuario
            session_id: ID de la sesión de reset
            email: Email del usuario

        Returns:
            Token JWT firmado
        """
        now = datetime.now(timezone.utc)
        exp = now + timedelta(minutes=JWTResetService.RESET_TOKEN_EXPIRY_MINUTES)

        payload = {
            "sub": str(user_id),  # JWT spec: subject must be a string
            "session_id": session_id,
            "email": email,
            "scope": JWTResetService.RESET_SCOPE,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
        }

        token = jwt.encode(
            payload,
            settings.SECRET_KEY,
            algorithm="HS256"
        )

        return token

    @staticmethod
    def verify_reset_token(token: str) -> Optional[Dict]:
        """
        Valida y decodifica reset_token.

        Args:
            token: JWT reset_token

        Returns:
            Payload decodificado si es válido, None si es inválido
        """
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=["HS256"]
            )

            # Validar scope
            if payload.get("scope") != JWTResetService.RESET_SCOPE:
                return None

            return payload

        except jwt.PyJWTError:
            # Token expirado o inválido. PyJWTError es la base de TODAS las
            # excepciones de PyJWT -- equivalente exacto al JWTError de
            # python-jose que capturaba esto mismo antes de la migración
            # (Ronda 10).
            return None


# ============================================================
# AUTENTICACIÓN DE DOBLE FACTOR - 2FA/TOTP (antes app/services/totp_service.py)
# ============================================================
# Genera y verifica códigos TOTP compatibles con Google Authenticator, Authy, etc.

# Contexto para hashear backup codes
_backup_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

ISSUER_NAME = "FileMeshy"


class TOTPService:

    @staticmethod
    def generate_secret() -> str:
        """Genera un secreto TOTP aleatorio en Base32."""
        return pyotp.random_base32()

    @staticmethod
    def get_provisioning_uri(secret: str, email: str) -> str:
        """Genera la URI otpauth:// para el QR."""
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=email, issuer_name=ISSUER_NAME)

    @staticmethod
    def generate_qr_base64(uri: str) -> str:
        """Genera un QR code como imagen PNG en base64."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return base64.b64encode(buffer.getvalue()).decode()

    @staticmethod
    def verify_code(secret: str, code: str) -> bool:
        """Verifica un código TOTP. Permite ventana de ±30 segundos (valid_window=1)."""
        if not secret or not code:
            return False
        try:
            totp = pyotp.TOTP(secret)
            return totp.verify(code.strip(), valid_window=1)
        except Exception:
            return False

    @staticmethod
    def generate_backup_codes(count: int = 8) -> tuple[list[str], list[str]]:
        """
        Genera backup codes.
        Retorna (plain_codes, hashed_codes).
        Los plain_codes se muestran al usuario una sola vez.
        Los hashed_codes se guardan en la BD.
        """
        plain = [f"{secrets.token_hex(3).upper()}-{secrets.token_hex(3).upper()}" for _ in range(count)]
        hashed = [_backup_ctx.hash(code) for code in plain]
        return plain, hashed

    @staticmethod
    def verify_backup_code(code: str, hashed_codes: list[str]) -> tuple[bool, list[str]]:
        """
        Verifica un backup code contra la lista hasheada.
        Si es válido, lo elimina de la lista (uso único).
        Retorna (válido, lista_actualizada).
        """
        code = code.strip().upper()
        for i, hashed in enumerate(hashed_codes):
            try:
                if _backup_ctx.verify(code, hashed):
                    remaining = hashed_codes[:i] + hashed_codes[i + 1:]
                    return True, remaining
            except Exception:
                continue
        return False, hashed_codes


# ============================================================
# RATE LIMITING (antes app/services/rate_limit_service.py)
# ============================================================
# Rate limiting respaldado por Redis (fallback a memoria si Redis no está disponible).

_rl_logger = logging.getLogger("filemeshy.rate_limit")

# In-memory fallback (used only when Redis is unavailable)
_memory_store: Dict[str, Dict] = {}
_memory_lockout_counts: Dict[str, Dict] = {}  # identifier -> {"count": int, "last": datetime}
_rl_lock = threading.Lock()
_memory_fixed_windows: Dict[str, Dict] = {}  # ventana fija (check_fixed_window)
# Umbral de entradas del fallback en memoria antes de purgar (cota de memoria).
MEMORY_FIXED_WINDOWS_MAX_ENTRIES = 10_000

# ===== LOCKOUT PROGRESIVO =====
# Escalada real (no un bloqueo fijo repetido): cada vez que la MISMA
# identidad (ip+email o email solo) dispara un bloqueo nuevo DESPUÉS de haber
# sido bloqueada una vez ya, el bloqueo siguiente es más largo -- sin esto,
# alguien puede seguir probando contraseñas indefinidamente, solo pausando
# `lock_duration` entre tandas. 15min -> 30min -> 1h -> 4h -> 24h (techo, no
# sigue creciendo después). El contador de "cuántas veces seguidas" vive en
# Redis con TTL largo (7 días) -- se resetea con un login exitoso (ver
# RateLimiter.clear) o solo, por inactividad total, a los 7 días.
LOCKOUT_PROGRESSION = [900, 1800, 3600, 14400, 86400]  # 15min, 30min, 1h, 4h, 24h
LOCKOUT_COUNT_TTL = 7 * 24 * 3600  # 7 días de inactividad resetea la escalada


def _format_lock_message(seconds: int) -> str:
    """Mensaje legible -- en minutos hasta 1h, en horas de ahí en adelante
    (1440 minutos es peor de leer que "24 horas")."""
    if seconds < 3600:
        remaining = max(1, seconds // 60)
        return f"Demasiados intentos. Intenta en {remaining} minutos"
    remaining = max(1, seconds // 3600)
    return f"Demasiados intentos. Intenta en {remaining} horas"


class RateLimiter:
    """Rate limiter using Redis with in-memory fallback."""

    @staticmethod
    def _get_redis():
        try:
            if cache.enabled and cache.client:
                return cache.client
        except Exception:
            pass
        return None

    @staticmethod
    def check_rate_limit(
        identifier: str,
        max_attempts: int = None,
        lock_duration: int = None,
        progressive: bool = False,
    ) -> Tuple[bool, str]:
        """max_attempts/lock_duration opcionales -- si no se pasan, usa los
        defaults globales (settings.RATE_LIMIT_*). Permite límites con otro
        umbral para el mismo mecanismo (ej: tope por email, más alto que el
        tope combinado ip+email de login).

        progressive=True: en vez de `lock_duration` fijo, cada bloqueo nuevo
        de esta identidad escala según LOCKOUT_PROGRESSION (ver arriba) --
        usado en /login (ip+email y el backstop por email), no en el resto de
        rate limits (password-reset, etc.) que no lo pidieron."""
        redis = RateLimiter._get_redis()
        if redis:
            return RateLimiter._check_redis(redis, identifier, max_attempts, lock_duration, progressive)
        return RateLimiter._check_memory(identifier, max_attempts, lock_duration, progressive)

    @staticmethod
    def record_attempt(identifier: str, window_seconds: int = 3600) -> None:
        redis = RateLimiter._get_redis()
        if redis:
            RateLimiter._record_redis(redis, identifier, window_seconds)
        else:
            RateLimiter._record_memory(identifier)

    @staticmethod
    def check_fixed_window(identifier: str, max_requests: int, window_seconds: int) -> Tuple[bool, str]:
        """Throttle de VENTANA FIJA: como máximo `max_requests` por ventana de
        `window_seconds`, contadas desde la primera request de la ventana (el
        TTL se fija solo al primer INCR, no se renueva). Cuenta y decide en
        una sola operación atómica. Distinto de check_rate_limit +
        record_attempt (que renuevan el TTL en cada intento y bloquean con
        lockout): se usa solo para los throttles de volumen de shares."""
        redis = RateLimiter._get_redis()
        if redis:
            try:
                key = f"rlfw:{identifier}"
                pipe = redis.pipeline()
                pipe.incr(key)
                pipe.ttl(key)
                count, ttl = pipe.execute()
                if int(count) == 1 or ttl is None or int(ttl) < 0:
                    redis.expire(key, window_seconds)
                    ttl = window_seconds
                if int(count) > max_requests:
                    return False, f"Demasiadas solicitudes. Intenta en {max(1, int(ttl))} segundos"
                return True, "OK"
            except Exception as exc:
                _rl_logger.warning("check_fixed_window Redis falló, usando memoria: %s", exc)
        with _rl_lock:
            now = time.monotonic()
            if len(_memory_fixed_windows) > MEMORY_FIXED_WINDOWS_MAX_ENTRIES:
                RateLimiter._purge_memory_fixed_windows(now)
            entry = _memory_fixed_windows.get(identifier)
            if entry is None or now - entry["start"] >= entry.get("window", window_seconds):
                entry = {"start": now, "count": 0, "window": window_seconds}
                _memory_fixed_windows[identifier] = entry
            entry["count"] += 1
            if entry["count"] > max_requests:
                remaining = max(1, int(window_seconds - (now - entry["start"])))
                return False, f"Demasiadas solicitudes. Intenta en {remaining} segundos"
            return True, "OK"

    @staticmethod
    def _purge_memory_fixed_windows(now: float) -> None:
        """Cota de memoria del fallback (Redis caído). Llamar con `_rl_lock`
        tomado. Primero descarta ventanas vencidas (cada entrada guarda su
        propia `window`); si aun así se supera el umbral, descarta las que
        vencen antes (las más viejas/más cerca de expirar) hasta bajar (cota
        dura), así una ventana larga de un atacante activo se conserva."""
        for key in [k for k, e in _memory_fixed_windows.items() if now - e["start"] >= e["window"]]:
            del _memory_fixed_windows[key]
        excess = len(_memory_fixed_windows) - MEMORY_FIXED_WINDOWS_MAX_ENTRIES
        if excess > 0:
            oldest = sorted(
                _memory_fixed_windows,
                key=lambda k: _memory_fixed_windows[k]["start"] + _memory_fixed_windows[k]["window"],
            )[:excess]
            for key in oldest:
                del _memory_fixed_windows[key]

    @staticmethod
    def clear(identifier: str) -> None:
        """Limpia los intentos Y la escalada de lockout progresivo -- llamar
        en cada login exitoso, para que la próxima vez que esta identidad
        dispare un bloqueo empiece de nuevo desde el más corto (15min), no
        continúe donde había quedado la escalada anterior."""
        redis = RateLimiter._get_redis()
        if redis:
            redis.delete(f"rl:{identifier}")
            redis.delete(f"rl_lockout_count:{identifier}")
        else:
            with _rl_lock:
                _memory_store.pop(identifier, None)
                _memory_lockout_counts.pop(identifier, None)

    # -- Redis implementation --

    @staticmethod
    def _next_lockout_seconds_redis(redis, identifier: str) -> int:
        """Incrementa el contador de bloqueos consecutivos (TTL largo,
        LOCKOUT_COUNT_TTL) y devuelve cuántos segundos debe durar ESTE
        bloqueo según la escalada."""
        count_key = f"rl_lockout_count:{identifier}"
        pipe = redis.pipeline()
        pipe.incr(count_key)
        pipe.expire(count_key, LOCKOUT_COUNT_TTL)
        count, _ = pipe.execute()
        idx = min(int(count) - 1, len(LOCKOUT_PROGRESSION) - 1)
        return LOCKOUT_PROGRESSION[idx]

    @staticmethod
    def _check_redis(
        redis, identifier: str, max_attempts: int = None, lock_duration: int = None, progressive: bool = False
    ) -> Tuple[bool, str]:
        max_attempts = max_attempts if max_attempts is not None else settings.RATE_LIMIT_MAX_ATTEMPTS
        lock_duration = lock_duration if lock_duration is not None else settings.RATE_LIMIT_LOCK_DURATION
        key = f"rl:{identifier}"
        lock_key = f"rl_lock:{identifier}"

        lock_ttl = redis.ttl(lock_key)
        if lock_ttl and lock_ttl > 0:
            return False, _format_lock_message(lock_ttl)

        attempts = redis.get(key)
        if attempts and int(attempts) >= max_attempts:
            actual_duration = (
                RateLimiter._next_lockout_seconds_redis(redis, identifier) if progressive else lock_duration
            )
            redis.setex(lock_key, actual_duration, "1")
            redis.delete(key)
            return False, _format_lock_message(actual_duration)

        return True, "OK"

    @staticmethod
    def _record_redis(redis, identifier: str, window_seconds: int = 3600) -> None:
        key = f"rl:{identifier}"
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        pipe.execute()

    # -- Memory fallback --

    @staticmethod
    def _next_lockout_seconds_memory(identifier: str, now: datetime) -> int:
        entry = _memory_lockout_counts.get(identifier)
        if not entry or (now - entry["last"]).total_seconds() > LOCKOUT_COUNT_TTL:
            count = 1
        else:
            count = entry["count"] + 1
        _memory_lockout_counts[identifier] = {"count": count, "last": now}
        idx = min(count - 1, len(LOCKOUT_PROGRESSION) - 1)
        return LOCKOUT_PROGRESSION[idx]

    @staticmethod
    def _check_memory(
        identifier: str, max_attempts: int = None, lock_duration: int = None, progressive: bool = False
    ) -> Tuple[bool, str]:
        max_attempts = max_attempts if max_attempts is not None else settings.RATE_LIMIT_MAX_ATTEMPTS
        lock_duration = lock_duration if lock_duration is not None else settings.RATE_LIMIT_LOCK_DURATION
        with _rl_lock:
            now = datetime.now(timezone.utc)
            entry = _memory_store.get(identifier)

            if not entry:
                _memory_store[identifier] = {
                    "attempts": 0,
                    "first_attempt": now,
                    "locked_until": None,
                }
                return True, "OK"

            if entry["locked_until"] and now < entry["locked_until"]:
                remaining_seconds = max(1, int((entry["locked_until"] - now).total_seconds()))
                return False, _format_lock_message(remaining_seconds)

            if entry["locked_until"] and now >= entry["locked_until"]:
                _memory_store[identifier] = {
                    "attempts": 0,
                    "first_attempt": now,
                    "locked_until": None,
                }
                return True, "OK"

            if (now - entry["first_attempt"]).total_seconds() > 3600:
                _memory_store[identifier] = {
                    "attempts": 0,
                    "first_attempt": now,
                    "locked_until": None,
                }
                return True, "OK"

            if entry["attempts"] >= max_attempts:
                actual_duration = (
                    RateLimiter._next_lockout_seconds_memory(identifier, now) if progressive else lock_duration
                )
                entry["locked_until"] = now + timedelta(seconds=actual_duration)
                return False, _format_lock_message(actual_duration)

            return True, "OK"

    @staticmethod
    def _record_memory(identifier: str) -> None:
        with _rl_lock:
            now = datetime.now(timezone.utc)
            entry = _memory_store.get(identifier)
            if entry:
                entry["attempts"] += 1
            else:
                _memory_store[identifier] = {
                    "attempts": 1,
                    "first_attempt": now,
                    "locked_until": None,
                }


# ============================================================
# HASH DE CÓDIGOS DE RESET (antes app/services/code_hash_service.py)
# ============================================================
# Genera y verifica códigos de 6 dígitos con hash seguro.

class CodeHashService:
    """Generación y validación de códigos de reset con hash."""

    @staticmethod
    def generate_code() -> str:
        """
        Genera código de 6 dígitos aleatorio.

        Returns:
            String de 6 dígitos numéricos
        """
        return secrets.randbelow(1000000).__str__().zfill(6)

    @staticmethod
    def hash_code(code: str) -> str:
        """
        Hashea un código usando SHA256.

        Args:
            code: Código en plano (ej: "123456")

        Returns:
            Hash SHA256 del código
        """
        return hashlib.sha256(code.encode()).hexdigest()

    @staticmethod
    def verify_code(plain_code: str, code_hash: str) -> bool:
        """
        Verifica que el código coincida con el hash.

        Args:
            plain_code: Código en plano del usuario
            code_hash: Hash guardado en BD

        Returns:
            True si coinciden, False si no
        """
        computed_hash = CodeHashService.hash_code(plain_code)
        return hmac.compare_digest(computed_hash, code_hash)

    @staticmethod
    def generate_session_id() -> str:
        """
        Genera session_id opaco (UUID-like) para la cookie.

        Returns:
            String aleatorio de 36 caracteres (UUID format)
        """
        return str(secrets.token_hex(18))


# ============================================================
# AUDITORÍA DE EVENTOS DE PASSWORD/LOGIN (antes app/services/audit_service.py)
# ============================================================
# Eventos de seguridad de password/login -- no escriben a la tabla audit_log
# (eso es responsabilidad de audit/service.py, un mecanismo distinto).

audit_logger = logging.getLogger("audit")


class AuditService:
    """Servicio para auditoría de seguridad."""

    @staticmethod
    def log_password_reset_request(
        email: str,
        ip_address: str,
        user_agent: str = None,
        user_exists: bool = False
    ) -> None:
        """
        Registra una solicitud de reset de contraseña.

        Args:
            email: Email del usuario
            ip_address: IP de origen
            user_agent: User agent del navegador
            user_exists: Si el usuario existe en el sistema
        """
        status_ = "SUCCESS" if user_exists else "NOT_FOUND"
        audit_logger.info(
            f"PASSWORD_RESET_REQUEST | email={email} | ip={ip_address} | status={status_} | ua={user_agent}"
        )

    @staticmethod
    def log_password_reset_attempt(
        email: str,
        ip_address: str,
        success: bool,
        reason: str = None,
        user_agent: str = None
    ) -> None:
        """
        Registra un intento de verificación de reset.

        Args:
            email: Email del usuario
            ip_address: IP de origen
            success: Si fue exitoso
            reason: Razón del fallo (opcional)
            user_agent: User agent del navegador
        """
        status_ = "SUCCESS" if success else f"FAILED({reason})"
        audit_logger.info(
            f"PASSWORD_RESET_VERIFY | email={email} | ip={ip_address} | status={status_} | ua={user_agent}"
        )

    @staticmethod
    def log_password_changed(
        user_id: UUID,
        email: str,
        ip_address: str,
        user_agent: str = None,
        method: str = "reset"  # "reset", "profile", "admin"
    ) -> None:
        """
        Registra un cambio exitoso de contraseña.

        Args:
            user_id: ID del usuario
            email: Email del usuario
            ip_address: IP de origen
            user_agent: User agent del navegador
            method: Método de cambio
        """
        audit_logger.warning(
            f"PASSWORD_CHANGED | user_id={user_id} | email={email} | ip={ip_address} | "
            f"method={method} | ua={user_agent}"
        )

    @staticmethod
    def log_suspicious_activity(
        email: str,
        ip_address: str,
        activity_type: str,
        details: str = None,
        user_agent: str = None
    ) -> None:
        """
        Registra actividades sospechosas.

        Args:
            email: Email del usuario
            ip_address: IP de origen
            activity_type: Tipo de actividad (ej: "multiple_resets", "different_ip", etc)
            details: Detalles adicionales
            user_agent: User agent del navegador
        """
        audit_logger.error(
            f"SUSPICIOUS_ACTIVITY | email={email} | ip={ip_address} | type={activity_type} | "
            f"details={details} | ua={user_agent}"
        )
