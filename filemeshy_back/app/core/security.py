import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import jwt  # PyJWT (Ronda 10: migrado desde python-jose, sin mantenimiento activo)
from passlib.context import CryptContext
from app.core.config import settings
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import uuid

logger = logging.getLogger("filemeshy.security")

# ===== CSRF (doble-submit cookie, defensa en profundidad ademas de
# SameSite=lax) ===== Cookie NO httponly a proposito: el frontend la lee por
# JS y la reenvia como header X-XSRF-TOKEN en cada request que muta estado
# (ver app/middleware/csrf.py). El valor no se guarda en ningun lado server-
# side -- el propio middleware solo compara cookie == header.
CSRF_COOKIE_NAME = "filemeshy_csrf_token"
CSRF_HEADER_NAME = "x-xsrf-token"


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response, token: str) -> None:
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )


def clear_csrf_cookie(response) -> None:
    response.delete_cookie(key=CSRF_COOKIE_NAME, secure=settings.COOKIE_SECURE, samesite="lax")


# ===== SESIONES APILADAS ("Cambiar de usuario") =====
# Cada sesion pausada por el flujo de "Cambiar de usuario" (ver
# filemeshy_front/src/shared/hooks/useAuth.ts::switchUser/returnToPreviousUser)
# tiene su PROPIA cookie httpOnly de refresh token, nombrada por su
# profundidad en la pila -- asi ninguna pisa a la de abajo.
# Prefijo "filemeshy_" en todas las cookies propias (no solo esta): las
# cookies se comparten por dominio SIN distinguir puerto, a diferencia de
# localStorage. En un mismo "localhost" con otro proyecto corriendo en otro
# puerto, una cookie sin prefijo (ej. la vieja "refresh_token") choca con la
# de ese otro proyecto y una pisa a la otra en el navegador (encontrado en
# vivo: refresh en loop infinito con 401, sesion invalidada por un
# login/logout del otro proyecto en otra pestaña).
MAX_SESSION_SLOTS = 4  # slot 0 (base) + hasta 3 sesiones pausadas


def refresh_cookie_name(slot: int) -> str:
    """Nombre de la cookie httpOnly de refresh token para un slot dado."""
    return "filemeshy_refresh_token" if slot == 0 else f"filemeshy_refresh_token_slot_{slot}"


# ===== PASSWORD HASHING =====
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña contra su hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Genera el hash de una contraseña."""
    return pwd_context.hash(password)


# ===== ENCRYPTION FOR SENSITIVE DATA (SMTP PASSWORD, API KEYS) =====
_fernet_cipher = None


def get_fernet_cipher():
    """Derives a Fernet key from SECRET_KEY using PBKDF2 (cached)."""
    global _fernet_cipher
    if _fernet_cipher is not None:
        return _fernet_cipher

    # Salt derivado del SECRET_KEY para que sea único por despliegue
    salt = hashlib.sha256(settings.SECRET_KEY.encode() + b"filemeshy_fernet_v1").digest()[:16]
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    derived = kdf.derive(settings.SECRET_KEY.encode())
    key = base64.urlsafe_b64encode(derived)
    _fernet_cipher = Fernet(key)
    return _fernet_cipher


def encrypt_sensitive_data(data: str) -> str:
    """
    Encripta datos sensibles (contraseñas SMTP, API keys, etc).
    
    Args:
        data: Datos en texto plano
        
    Returns:
        Datos encriptados (string decodificado)
    """
    try:
        cipher = get_fernet_cipher()
        encrypted = cipher.encrypt(data.encode())
        return encrypted.decode()
    except Exception:
        logger.error("Error encrypting sensitive data")
        raise


def decrypt_sensitive_data(encrypted_data: str) -> str:
    """
    Desencripta datos sensibles.
    
    Args:
        encrypted_data: Datos encriptados
        
    Returns:
        Datos en texto plano
    """
    try:
        cipher = get_fernet_cipher()
        decrypted = cipher.decrypt(encrypted_data.encode())
        return decrypted.decode()
    except Exception:
        logger.error("Error decrypting sensitive data")
        raise


def is_encrypted_token(value: Optional[str]) -> bool:
    """True si `value` es un token Fernet válido para ESTA instalación (se
    descifra con la clave derivada del SECRET_KEY)."""
    if not value:
        return False
    try:
        get_fernet_cipher().decrypt(value.encode())
        return True
    except Exception:
        return False


def encrypt_secret_if_needed(value: Optional[str]) -> Optional[str]:
    """Cifra `value` con el mismo mecanismo Fernet de `encrypt_sensitive_data`,
    salvo que ya sea un token válido (idempotente: evita el doble cifrado si
    un camino ya cifró antes de llegar al repositorio). Vacío/None se devuelve tal cual."""
    if not value or is_encrypted_token(value):
        return value
    return encrypt_sensitive_data(value)


def decrypt_secret_tolerant(value: Optional[str]) -> Optional[str]:
    """Descifra un secreto guardado en `system_configuration`. TOLERA valores
    legados en CLARO: si no es un token Fernet válido, lo devuelve tal cual
    (así no se rompen instalaciones cuyo secreto se guardó sin cifrar; se
    cifra recién cuando se vuelve a guardar). Nunca loguea el valor."""
    if not value:
        return value
    try:
        return get_fernet_cipher().decrypt(value.encode()).decode()
    except Exception:
        # Ronda 12d: un valor con forma de token Fernet ("gAAAAA...") que NO se descifra
        # (típico: cambió SECRET_KEY) no es una contraseña en claro; devolver el ciphertext
        # hacía fallar el SMTP/CAPTCHA sin aviso. Se loguea un ERROR claro (sin el valor) y
        # se devuelve None.
        if value.startswith("gAAAAA"):
            logger.error(
                "No se pudo descifrar un secreto guardado (¿cambió SECRET_KEY?): hay que "
                "volver a guardarlo desde la configuración. Se usa como si no estuviera configurado."
            )
            return None
        return value


# ===== JWT TOKENS =====
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None, jti: Optional[str] = None) -> Tuple[str, str]:
    """Crea un token JWT de acceso con JTI único.
    
    Returns:
        Tuple[str, str]: (token, jti)
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    
    # Generar JTI único si no se proporciona
    if jti is None:
        jti = str(uuid.uuid4())
    
    to_encode.update({"exp": expire, "jti": jti})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt, jti


def create_refresh_token(data: dict, jti: Optional[str] = None) -> Tuple[str, str]:
    """Crea un token JWT de refresco con JTI único.
    
    Returns:
        Tuple[str, str]: (token, jti)
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    # Generar JTI único si no se proporciona
    if jti is None:
        jti = str(uuid.uuid4())
    
    to_encode.update({"exp": expire, "type": "refresh", "jti": jti})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt, jti


def encrypt_totp_secret(secret: str) -> str:
    """Cifra un secreto TOTP antes de guardarlo en BD."""
    return encrypt_sensitive_data(secret)


def decrypt_totp_secret(stored: str) -> str:
    """
    Descifra un secreto TOTP.
    Fallback: si el valor no está cifrado (legacy en texto plano), lo devuelve tal cual.
    Esto permite migración transparente — los secrets existentes siguen funcionando.
    """
    try:
        return decrypt_sensitive_data(stored)
    except Exception:
        # Secret legacy en texto plano — devolver sin cambios
        return stored


def create_pre_auth_token(email: str) -> str:
    """Crea un token de pre-autenticación para el paso 2FA (válido 5 minutos)."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    jti = str(uuid.uuid4())
    to_encode = {"sub": email, "type": "pre_auth", "exp": expire, "jti": jti}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decodifica un token JWT."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except jwt.PyJWTError:
        # PyJWTError es la base de TODAS las excepciones de PyJWT (firma
        # inválida, expirado, malformado, algoritmo no permitido, etc.) --
        # equivalente exacto al JWTError de python-jose que capturaba esto
        # mismo antes de la migración (Ronda 10). Catch amplio a propósito:
        # cualquier excepción no capturada acá se propagaría como 500 en vez
        # del 401 esperado en app/auth/service.py::get_current_user.
        return None
