import re
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.core.logging_config import app_logger
from app.users.schemas import (
    UserCreate,
    LoginRequest,
    User as UserSchema,
    RefreshTokenRequest,
    TwoFactorSetupResponse,
    TwoFactorStatus,
    TwoFactorVerifyRequest,
    TwoFactorDisableRequest,
    TwoFactorLoginResponse,
    TwoFactorLoginVerify,
)
from app.auth.schemas import (
    PasswordResetRequest,
    PasswordResetVerify,
    PasswordResetConfirm,
)
from app.auth.schemas import (
    PasswordResetErrorCode,
)
from app.shared.schemas.common import SuccessResponse
from app.users.service import user_service
from app.auth.repository import CRUDPasswordResetSession
from app.auth.service import AuthService
from app.notifications.service import EmailService
from app.auth.service import RateLimiter
from app.auth.service import AuditService
from app.auth.service import CodeHashService
from app.auth.service import JWTResetService
from app.access_control.service import permission_mapper
from app.core.password_validator import password_validator
from app.auth.service import get_current_active_user
from app.users.models import User
from app.core.security import (
    generate_csrf_token,
    set_csrf_cookie,
    clear_csrf_cookie,
    refresh_cookie_name,
    MAX_SESSION_SLOTS,
)


def _is_desktop_client(request: Request) -> bool:
    """La app de escritorio (Tauri) es cross-origin contra el backend siempre
    -- la cookie refresh_token (SameSite=lax) nunca le llega. Se identifica
    con este header para mandarle el refresh_token tambien en el body."""
    return request.headers.get("x-client-type", "").lower() == "desktop"


def _get_session_slot(request: Request) -> int:
    """Lee X-Session-Slot (entero, default 0 si no viene o es invalido) --
    dice que cookie de refresh mirar/escribir (ver refresh_cookie_name). No
    valida el techo aca: eso lo hace login(), que es el unico lugar donde se
    "crea" un slot nuevo. refresh/logout solo leen slots que ya existen -- si
    no existen, el 401 (cookie ausente) o el no-op (nada que cerrar) los frena
    sin necesidad de repetir la validacion de techo."""
    raw = request.headers.get("x-session-slot", "0")
    try:
        slot = int(raw)
    except (TypeError, ValueError):
        return 0
    return slot if slot >= 0 else 0


_SLOT_COOKIE_PATTERN = re.compile(r"^filemeshy_refresh_token_slot_\d+$")


def _sweep_orphan_slot_cookies(db: Session, request: Request, response: Response, user_id) -> None:
    """Desactiva y borra cualquier cookie filemeshy_refresh_token_slot_N presente en un
    login "de base" (slot 0) que pertenezca al MISMO usuario que esta
    logueando ahora -- cubre el caso de un "cambiar de usuario" incompleto
    (ej. F5 a mitad de un switch: la pila de JS se pierde, pero la cookie y
    la Session en la BD seguian vivas hasta su expires_at natural).

    Si la cookie pertenece a OTRO usuario (equipo compartido: alguien mas
    tenia una sesion pausada en este mismo navegador), no se toca -- ni se
    desactiva su Session ni se borra su cookie. Sin esto, un login cualquiera
    de un tercero cerraria en silencio, sin auditoria, la sesion pausada de
    otra persona (hallazgo de auditoria de seguridad).

    Best-effort a proposito en el resto: nunca debe bloquear un login
    legitimo."""
    from app.auth.models import Session as SessionModel

    for cookie_name in list(request.cookies.keys()):
        if not _SLOT_COOKIE_PATTERN.match(cookie_name):
            continue
        try:
            token_value = request.cookies.get(cookie_name)
            payload = decode_token(token_value) if token_value else None
            jti = payload.get("jti") if payload else None
            session = None
            if jti:
                session = db.query(SessionModel).filter(
                    SessionModel.refresh_token_jti == jti
                ).first()

            if session and str(session.user_id) != str(user_id):
                # Sesion pausada de otro usuario -- no tocar.
                continue

            if session:
                session.is_active = False
                db.commit()
                log_audit(
                    db=db,
                    request=request,
                    user_id=str(session.user_id),
                    user_email=None,
                    action="LOGOUT",
                    table_name="sessions",
                    record_id=session.id,
                    new_data={
                        "ip": request.client.host if request.client else None,
                        "cookie": cookie_name,
                        "reason": "orphan_slot_sweep",
                    },
                )
            # Cookie invalida/sin Session real, o del propio usuario (ya
            # cerrada arriba) -- en ambos casos no sirve para nada mas.
            response.delete_cookie(
                key=cookie_name, httponly=True, secure=settings.COOKIE_SECURE, samesite="lax"
            )
        except Exception:
            app_logger.warning("No se pudo limpiar la cookie huerfana %s en login", cookie_name)


def _close_session_cookie(db: Session, request: Request, response: Response, cookie_name: str) -> None:
    """Desactiva la Session (si existe) atada a la cookie dada y la borra de
    la respuesta. Usado por logout: scope=all la llama para cada cookie
    presente (filemeshy_refresh_token + filemeshy_refresh_token_slot_*), scope=current para una
    sola (la del slot activo)."""
    from app.auth.models import Session as SessionModel

    refresh_token_value = request.cookies.get(cookie_name)
    if refresh_token_value:
        payload = decode_token(refresh_token_value)
        if payload:
            refresh_jti = payload.get("jti")
            if refresh_jti:
                session = db.query(SessionModel).filter(
                    SessionModel.refresh_token_jti == refresh_jti
                ).first()
                if session:
                    session.is_active = False
                    db.commit()
                    from app.auth.service import invalidate_session_active_cache
                    invalidate_session_active_cache(session.access_token_jti)
                    log_audit(
                        db=db,
                        request=request,
                        user_id=str(session.user_id),
                        user_email=None,
                        action="LOGOUT",
                        table_name="sessions",
                        record_id=session.id,
                        new_data={
                            "ip": request.client.host if request.client else None,
                            "cookie": cookie_name,
                        },
                    )
    response.delete_cookie(key=cookie_name, httponly=True, secure=settings.COOKIE_SECURE, samesite="lax")


from app.audit.service import log_audit
from app.core.security import decode_token, encrypt_totp_secret, decrypt_totp_secret
from app.auth.service import TOTPService
from app.configuration.service import get_system_config
import httpx

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Utilidades internas — Turnstile + detección de IP
# ---------------------------------------------------------------------------

def _get_real_ip(request: Request) -> str:
    """Obtiene la IP real del cliente.

    `direct_ip` (request.client.host) es la IP de la conexión TCP real -- la
    única que ningún cliente puede falsificar. Los headers CF-Connecting-IP
    (Cloudflare) y X-Real-IP (nginx) SOLO se confían si `direct_ip` está en
    `settings.TRUSTED_PROXY_IPS` -- es decir, si la request de verdad pasó
    por un proxy conocido que los pone. Sin esta validación, cualquier
    cliente podía mandar esos headers con el valor que quisiera y evadir por
    completo el rate-limit/CAPTCHA por IP de /auth (hallazgo de auditoría de
    seguridad -- confirmado en vivo rotando X-Real-IP contra /auth/register).
    """
    direct_ip = request.client.host if request.client else "unknown"
    if direct_ip not in settings.TRUSTED_PROXY_IPS:
        return direct_ip
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return direct_ip


def _is_local_ip(ip: str) -> bool:
    """Retorna True si la IP es de red privada/local."""
    return bool(re.match(
        r"^(localhost|::1|127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)",
        ip
    )) or ip == "unknown"


async def _verify_turnstile(token: str, secret_key: str, ip: str) -> bool:
    """Verifica el token de Turnstile con la API de Cloudflare."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": secret_key, "response": token, "remoteip": ip},
            )
            result = resp.json()
            return result.get("success", False)
    except Exception as exc:
        app_logger.warning("Turnstile verification error: %s", exc)
        return False


# OPTIONS handler para preflight CORS
@router.options("/{path:path}", tags=["cors"])
async def options_handler(path: str):
    """Handler para requests OPTIONS (CORS preflight)."""
    return Response(status_code=200)


@router.get("/turnstile-config", tags=["auth"])
def get_turnstile_config(db: Session = Depends(get_db)):
    """Retorna si Turnstile está habilitado y la site key pública.
    Endpoint público — no requiere autenticación.
    """
    enabled_cfg = get_system_config(db, "turnstile_enabled")
    site_key_cfg = get_system_config(db, "turnstile_site_key")
    return {
        "enabled": bool(enabled_cfg.value_boolean) if enabled_cfg else False,
        "site_key": site_key_cfg.value_string or "" if site_key_cfg else "",
    }


@router.post("/register", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Registra un nuevo usuario."""
    import re

    # Flag de registro público -- mismo patrón de lectura de config que usa
    # GET /public/config (app/platform/router.py) para reportar este mismo
    # valor al frontend. Antes de este fix, un admin podía "apagar" el
    # registro desde el panel y /auth/register igual devolvía 201 (hallazgo
    # de auditoría de seguridad, ver pendiente.md). Solo bloquea si el flag
    # existe y está EXPLÍCITAMENTE en false -- si todavía no se configuró
    # nada (config inexistente), el registro sigue permitido, igual que el
    # comportamiento de siempre.
    registration_cfg = get_system_config(db, "user_registration_enabled")
    if registration_cfg is not None and registration_cfg.value_boolean is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El registro de nuevos usuarios está deshabilitado",
        )

    ip_address = _get_real_ip(request)

    # Rate limiting por IP -- mismo patrón que /login y /password-reset/request.
    # Sin esto, /register no tenía ningún límite (a diferencia del resto de
    # endpoints públicos de auth), permitiendo automatizar registros masivos.
    rl_key_ip = f"register:ip:{ip_address}"
    is_allowed_ip, rl_message_ip = RateLimiter.check_rate_limit(
        rl_key_ip, max_attempts=8, lock_duration=3600
    )
    if not is_allowed_ip:
        raise HTTPException(status_code=429, detail=rl_message_ip)
    RateLimiter.record_attempt(rl_key_ip)

    # Validar Turnstile si está habilitado y la petición viene de IP pública
    # -- mismo criterio que /login.
    if not _is_local_ip(ip_address):
        enabled_cfg = get_system_config(db, "turnstile_enabled")
        if enabled_cfg and enabled_cfg.value_boolean:
            if not user_in.turnstile_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Se requiere verificación CAPTCHA para acceso externo",
                )
            secret_cfg = get_system_config(db, "turnstile_secret_key")
            secret_key = secret_cfg.value_string if secret_cfg else ""
            if not secret_key:
                app_logger.error("Turnstile habilitado pero sin secret_key configurada")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error de configuración del servidor",
                )
            valid = await _verify_turnstile(user_in.turnstile_token, secret_key, ip_address)
            if not valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Verificación CAPTCHA inválida o expirada",
                )

    # Validar complejidad de password
    pwd = user_in.password
    if len(pwd) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres")
    if not re.search(r'[A-Z]', pwd):
        raise HTTPException(status_code=400, detail="La contraseña debe contener al menos una mayúscula")
    if not re.search(r'[a-z]', pwd):
        raise HTTPException(status_code=400, detail="La contraseña debe contener al menos una minúscula")
    if not re.search(r'\d', pwd):
        raise HTTPException(status_code=400, detail="La contraseña debe contener al menos un número")

    existing_user = user_service.get_by_email(db, email=user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El email ya está registrado"
        )

    # Endpoint público y sin sesión (ver csrf.py) -- nunca confiar en el role_id
    # que mande el caller. La auto-registración siempre cae al rol USER por
    # defecto que ya aplica users/service.py::UserService.create cuando role_id
    # es None. Crear usuarios con otro rol requiere el endpoint autenticado
    # POST /users.
    user_in.role_id = None

    user = user_service.create(db, obj_in=user_in)
    return user


@router.post("/login", response_model=SuccessResponse)
async def login(
    login_request: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Autentica un usuario y retorna los tokens con refresh en httpOnly cookie.

    Tambien es el endpoint que usa "Cambiar de usuario" (ver useAuth.switchUser
    en el frontend) para loguear un usuario nuevo SIN pisar la cookie del que
    queda pausado -- el header X-Session-Slot (ver _get_session_slot) le dice
    a este endpoint en que cookie (filemeshy_refresh_token o
    filemeshy_refresh_token_slot_N) guardar el refresh token nuevo."""
    ip_address = _get_real_ip(request)

    slot = _get_session_slot(request)
    if slot > MAX_SESSION_SLOTS - 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Demasiadas sesiones pausadas simultáneas (máximo {MAX_SESSION_SLOTS - 1}).",
        )

    # Validar Turnstile si está habilitado y la petición viene de IP pública
    if not _is_local_ip(ip_address):
        enabled_cfg = get_system_config(db, "turnstile_enabled")
        if enabled_cfg and enabled_cfg.value_boolean:
            if not login_request.turnstile_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Se requiere verificación CAPTCHA para acceso externo",
                )
            secret_cfg = get_system_config(db, "turnstile_secret_key")
            secret_key = secret_cfg.value_string if secret_cfg else ""
            if not secret_key:
                app_logger.error("Turnstile habilitado pero sin secret_key configurada")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error de configuración del servidor",
                )
            valid = await _verify_turnstile(login_request.turnstile_token, secret_key, ip_address)
            if not valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Verificación CAPTCHA inválida o expirada",
                )

    # Rate limiting by IP + email. progressive=True: cada bloqueo nuevo de
    # esta combinación ip+email escala (15min -> 30min -> 1h -> 4h -> 24h) en
    # vez de ser siempre el mismo lock_duration fijo -- sin esto, alguien
    # puede seguir probando contraseñas indefinidamente, solo esperando el
    # mismo bloqueo corto entre tandas.
    rl_key = f"login:{ip_address}:{login_request.email}"
    is_allowed, rl_message = RateLimiter.check_rate_limit(rl_key, progressive=True)
    if not is_allowed:
        raise HTTPException(status_code=429, detail=rl_message)

    # Rate limiting adicional SOLO por email, sin importar la IP de origen --
    # el límite de arriba (ip+email) es evadible rotando IP (proxies, VPN,
    # botnet); este backstop cubre ese caso con un tope más alto (20/hora)
    # para no afectar el uso normal desde IPs distintas (oficina/casa/móvil).
    rl_key_email_only = f"login:email:{login_request.email}"
    is_allowed_email, rl_message_email = RateLimiter.check_rate_limit(
        rl_key_email_only, max_attempts=20, lock_duration=3600, progressive=True
    )
    if not is_allowed_email:
        raise HTTPException(status_code=429, detail=rl_message_email)

    try:
        user_agent = request.headers.get("user-agent")

        result = AuthService.login(
            db,
            email=login_request.email,
            password=login_request.password,
            ip_address=ip_address,
            user_agent=user_agent
        )

        # Clear rate limit on success
        RateLimiter.clear(rl_key)
        RateLimiter.clear(rl_key_email_only)

        # Si el usuario tiene 2FA, retornar pre_auth_token (sin tokens completos)
        if isinstance(result, TwoFactorLoginResponse):
            return SuccessResponse(
                status=200,
                message="Se requiere autenticación de doble factor",
                data=result.model_dump()
            )

        tokens = result

        # Auditar login exitoso -- distinguido de un "cambiar de usuario"
        # (slot > 0) para que quede trazable en la auditoria quien paso a
        # loguearse encima de quien, en vez de verse como un LOGIN mas.
        log_audit(
            db=db,
            request=request,
            user_id=str(tokens.user.id),
            user_email=tokens.user.email,
            action="SWITCH_USER" if slot > 0 else "LOGIN",
            table_name="sessions",
            record_id=tokens.user.id,
            new_data={"email": tokens.user.email, "ip": ip_address, "slot": slot},
        )

        # Establecer refresh token en httpOnly cookie -- una por slot (ver
        # "Cambiar de usuario"). Slot 0 = cookie "filemeshy_refresh_token",
        # "Recuérdame" → 30 días, normal → 7 días. Slots >=1 son sesiones
        # pausadas transitorias (soporte tecnico logueado encima de otro
        # usuario): TTL fijo de 7 dias siempre, sin importar remember_me --
        # no estan pensadas para persistir semanas como una sesion "de base".
        if slot == 0:
            cookie_max_age = 30 * 24 * 60 * 60 if login_request.remember_me else 7 * 24 * 60 * 60
        else:
            cookie_max_age = 7 * 24 * 60 * 60
        response.set_cookie(
            key=refresh_cookie_name(slot),
            value=tokens.refresh_token,
            max_age=cookie_max_age,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite="lax"
        )
        set_csrf_cookie(response, generate_csrf_token())

        # Login "de base" (slot 0): barrer cookies de slots >=1 huerfanas que
        # hayan quedado de un "cambiar de usuario" incompleto (ver
        # _sweep_orphan_slot_cookies).
        if slot == 0:
            _sweep_orphan_slot_cookies(db, request, response, tokens.user.id)

        login_data = {
            "access_token": tokens.access_token,
            "token_type": "bearer",
            "user": tokens.user.model_dump()
        }
        if _is_desktop_client(request):
            login_data["refresh_token"] = tokens.refresh_token

        return SuccessResponse(
            status=200,
            message="Login exitoso",
            data=login_data
        )
    except ValueError as e:
        RateLimiter.record_attempt(rl_key)
        RateLimiter.record_attempt(rl_key_email_only)
        log_audit(
            db=db,
            request=request,
            user_id=None,
            user_email=login_request.email,
            action="LOGIN_FAIL",
            table_name="sessions",
            record_id=login_request.email,
            new_data={"email": login_request.email, "ip": ip_address, "reason": str(e)},
        )
        # Worker: detectar múltiples fallos desde la misma IP
        try:
            from app.users.models import User as UserModel
            fail_user = db.query(UserModel).filter(UserModel.email == login_request.email).first()
            if fail_user:
                from app.core.database import tenant_schema_ctx
                from app.worker.tasks.security import notify_login_failures
                notify_login_failures.apply_async(
                    args=[tenant_schema_ctx.get(), fail_user.id, ip_address],
                    queue="critical",
                )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception:
        import logging
        logging.getLogger("filemeshy.auth").exception("Login error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )


@router.post("/refresh", response_model=SuccessResponse)
def refresh_token(
    request: Request,
    response: Response,
    body: RefreshTokenRequest = RefreshTokenRequest(),
    db: Session = Depends(get_db)
):
    """Refresca el access token usando el refresh token de la cookie del slot
    activo (web, ver X-Session-Slot/_get_session_slot) o del body (escritorio,
    ver _is_desktop_client)."""
    try:
        slot = _get_session_slot(request)
        # Cookie del slot pedido primero -- fallback al body solo para
        # desktop (cross-origin, nunca manda cookies). NUNCA cae a la cookie
        # de OTRO slot si la del slot pedido no esta presente: eso
        # reintroduciria el bug de raiz que este mecanismo existe para
        # arreglar (reautenticar en silencio con la identidad equivocada).
        refresh_token_value = request.cookies.get(refresh_cookie_name(slot)) or body.refresh_token
        if not refresh_token_value:
            raise ValueError("Refresh token no encontrado en cookies")

        # Refrescar el access token y rotar el refresh token
        access_token, new_refresh_token = AuthService.refresh_access_token(
            db,
            refresh_token=refresh_token_value
        )

        # Actualizar la cookie del MISMO slot con el nuevo refresh token
        response.set_cookie(
            key=refresh_cookie_name(slot),
            value=new_refresh_token,
            max_age=7 * 24 * 60 * 60,  # 7 días
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite="lax"
        )
        # Rotar tambien el CSRF token junto con el refresh token
        set_csrf_cookie(response, generate_csrf_token())

        refresh_data = {"access_token": access_token, "token_type": "bearer"}
        if _is_desktop_client(request):
            refresh_data["refresh_token"] = new_refresh_token

        return SuccessResponse(
            status=200,
            message="Token refrescado exitosamente",
            data=refresh_data
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se pudo refrescar el token"
        )


@router.post("/logout", response_model=SuccessResponse)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    scope: str = Query("all"),
):
    """Cierra sesión.

    `scope=all` (default -- comportamiento de siempre, botón "Cerrar sesión"):
    cierra TODAS las sesiones de este navegador, la de base (slot 0) y
    cualquier sesión pausada por "Cambiar de usuario" (slots >=1) -- recorre
    la cookie `filemeshy_refresh_token` mas cualquier
    `filemeshy_refresh_token_slot_*` presente.

    `scope=current` (nuevo): cierra SOLO la sesión del slot activo
    (X-Session-Slot), dejando las demás pausadas intactas. Lo usa el frontend
    (`closeActiveSessionOnBackend`) justo antes de "Volver" a una sesión
    pausada, para no dejar viva del lado del backend la sesión temporal que
    se abandona.
    """
    if scope not in ("all", "current"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scope inválido: debe ser 'all' o 'current'",
        )

    if scope == "current":
        cookie_names = [refresh_cookie_name(_get_session_slot(request))]
    else:
        cookie_names = [refresh_cookie_name(0)] + [
            name for name in request.cookies if _SLOT_COOKIE_PATTERN.match(name)
        ]

    try:
        for cookie_name in cookie_names:
            _close_session_cookie(db, request, response, cookie_name)

        if scope == "all":
            response.delete_cookie(key="filemeshy_password_reset_session", path="/api/v1/auth/password-reset")
            clear_csrf_cookie(response)

        return SuccessResponse(
            status=200,
            message="Sesión actual cerrada" if scope == "current" else "Logout exitoso",
            data=None
        )
    except Exception:
        # Aunque falle, limpiar las cookies que correspondan igual
        for cookie_name in cookie_names:
            response.delete_cookie(key=cookie_name, httponly=True, secure=settings.COOKIE_SECURE, samesite="lax")
        if scope == "all":
            response.delete_cookie(key="filemeshy_password_reset_session", path="/api/v1/auth/password-reset")
            clear_csrf_cookie(response)
        return SuccessResponse(
            status=200,
            message="Sesión actual cerrada" if scope == "current" else "Logout exitoso",
            data=None
        )


@router.get("/me", response_model=SuccessResponse)
def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtiene la información del usuario actual con permisos normalizados."""
    from app.configuration.service import get_user_preferences

    # Obtener preferencias del usuario para incluir el tema
    user_prefs = get_user_preferences(db, str(current_user.id))

    # Convertir usuario a schema y agregar tema
    user_schema = UserSchema.model_validate(current_user)

    # Llenar el campo role desde la relación role_obj
    if current_user.role_obj:
        user_schema.role = current_user.role_obj.name

    if user_prefs:
        user_schema.theme = user_prefs.theme
    else:
        user_schema.theme = "auto"

    # Normalizar permisos al formato canónico antes de devolver
    user_schema.permissions = permission_mapper.normalize_permissions(current_user.permissions, db=db)

    return SuccessResponse(
        status=200,
        message="Usuario obtenido exitosamente",
        data=user_schema.model_dump()
    )


@router.post("/password-reset/request", response_model=SuccessResponse)
def request_password_reset(
    request_data: PasswordResetRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    🔐 PASO 1: Solicita código para restablecer contraseña

    SEGURIDAD:
    1. NO revela si el usuario existe (respuesta idéntica)
    2. Envía código SOLO por email, nunca en respuesta
    3. Guarda HASH del código en BD (no el código plano)
    4. Cookie session_id opaco (UUID) para identificar sesión
    5. Rate limiting y auditoría completa
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "unknown")

    # Rate limiting por IP y por email -- mismo patrón que /login. Sin esto,
    # este endpoint permitía disparar emails/códigos de reset sin límite
    # (spam de correo, y fuerza bruta del código de 6 dígitos indirectamente
    # vía sesiones de reset nuevas).
    # El límite por IP usa un tope más alto (20/hora, igual que el backstop
    # por-email de /login) en vez del default global (5/15min): a diferencia
    # del límite por email (que solo afecta a la víctima de un intento de
    # reset ajeno), este es compartido por TODOS los usuarios detrás de la
    # misma IP -- con el default estricto, una sola oficina/NAT con varias
    # personas pidiendo reset en la misma hora se bloquea entre sí.
    rl_key_ip = f"password-reset:ip:{ip_address}"
    rl_key_email = f"password-reset:email:{request_data.email}"
    is_allowed_ip, rl_message_ip = RateLimiter.check_rate_limit(
        rl_key_ip, max_attempts=20, lock_duration=3600
    )
    if not is_allowed_ip:
        raise HTTPException(status_code=429, detail=rl_message_ip)
    is_allowed_email, rl_message_email = RateLimiter.check_rate_limit(rl_key_email)
    if not is_allowed_email:
        raise HTTPException(status_code=429, detail=rl_message_email)
    RateLimiter.record_attempt(rl_key_ip)
    RateLimiter.record_attempt(rl_key_email)

    # Verificar que el usuario existe
    user = user_service.get_by_email(db, email=request_data.email)
    user_exists = user is not None

    # Auditoría: Registrar intento
    AuditService.log_password_reset_request(
        email=request_data.email,
        ip_address=ip_address,
        user_agent=user_agent,
        user_exists=user_exists
    )

    # Respuesta idéntica si usuario no existe (seguridad)
    if not user:
        return SuccessResponse(
            message="Si el correo existe en nuestro sistema, recibirás un código de verificación",
            data={"expires_in_minutes": 15}
        )

    # Generar código aleatorio (6 dígitos)
    code = CodeHashService.generate_code()

    # Crear sesión de reset (guarda HASH del código, no el plano)
    reset_session = CRUDPasswordResetSession.create_session(
        db=db,
        user_id=user.id,
        email=user.email,
        code=code,
        expires_in_minutes=15
    )

    # ✅ SEGURIDAD: Cookie con session_id opaco (no el código)
    response.set_cookie(
        key="filemeshy_password_reset_session",
        value=reset_session.session_id,
        max_age=15 * 60,  # 15 minutos
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        path="/api/v1/auth/password-reset"
    )

    # Enviar código por email
    email_sent = EmailService.send_password_reset_code(
        email=user.email,
        code=code,
        business_name="FileMeshy",
        db=db
    )

    if email_sent:
        app_logger.info(f"[EMAIL] Código enviado a {user.email}")
    else:
        # En desarrollo, mostrar SOLO en logs (no en respuesta)
        app_logger.debug(f"[DEV] Código para {user.email}: {code}")

    # Respuesta: NUNCA incluir el código
    return SuccessResponse(
        message="Si el correo existe en nuestro sistema, recibirás un código de verificación",
        data={"expires_in_minutes": 15}
    )


@router.post("/password-reset/verify", response_model=SuccessResponse)
def verify_password_reset_code(
    verify_data: PasswordResetVerify,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    🔐 PASO 2: Verifica código y genera reset_token temporal

    SEGURIDAD:
    1. Valida código contra HASH guardado
    2. Rate limiting: máx 5 intentos
    3. Invalida código inmediatamente después de verificar
    4. Genera JWT reset_token (TTL 5 min, scope password_reset)
    5. Session_id se invalida después (uso único)
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "unknown")

    # Obtener session_id de cookie
    session_id = request.cookies.get("filemeshy_password_reset_session")

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=PasswordResetErrorCode.SESSION_NOT_FOUND
        )

    # Obtener sesión
    reset_session = CRUDPasswordResetSession.get_by_session_id(db, session_id)

    if not reset_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=PasswordResetErrorCode.SESSION_EXPIRED
        )

    # ===== RATE LIMITING: 5 intentos máximo =====
    if reset_session.code_attempts >= 5:
        AuditService.log_suspicious_activity(
            email=reset_session.email,
            ip_address=ip_address,
            activity_type="max_attempts_exceeded",
            details="5 intentos fallidos en /verify",
            user_agent=user_agent
        )
        raise HTTPException(
            status_code=429,
            detail=PasswordResetErrorCode.MAX_ATTEMPTS_EXCEEDED
        )

    # Validar código contra hash
    is_valid, message = CRUDPasswordResetSession.verify_code(
        db=db,
        session_id=session_id,
        code=verify_data.code,
        max_attempts=5
    )

    if not is_valid:
        AuditService.log_password_reset_attempt(
            email=reset_session.email,
            ip_address=ip_address,
            success=False,
            reason=message,
            user_agent=user_agent
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=PasswordResetErrorCode.INVALID_CODE
        )

    # ✅ Código válido: Generar reset_token JWT
    reset_token = JWTResetService.generate_reset_token(
        user_id=reset_session.user_id,
        session_id=session_id,
        email=reset_session.email
    )

    # Auditoría: Código verificado correctamente
    AuditService.log_password_reset_attempt(
        email=reset_session.email,
        ip_address=ip_address,
        success=True,
        reason="code_verified",
        user_agent=user_agent
    )

    # Enviar reset_token como cookie httpOnly (no en body)
    response.set_cookie(
        key="filemeshy_password_reset_token",
        value=reset_token,
        max_age=300,  # 5 minutos
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        path="/api/v1/auth/password-reset"
    )

    return SuccessResponse(
        message="Código verificado. Ahora establece tu nueva contraseña",
        data={}
    )


@router.post("/password-reset/confirm", response_model=SuccessResponse)
def confirm_password_reset(
    confirm_data: PasswordResetConfirm,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    🔐 PASO 3: Confirma reset_token y cambia contraseña

    SEGURIDAD:
    1. Valida JWT reset_token (firma, expiración, scope)
    2. Valida nueva contraseña (complejidad, no reutilizada)
    3. Cambia password con bcrypt
    4. Invalida reset_token (uso único)
    5. Invalida todas las sesiones activas del usuario
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "unknown")

    # Obtener reset_token: primero desde cookie httpOnly, fallback al body (legacy)
    reset_token = request.cookies.get("filemeshy_password_reset_token") or confirm_data.reset_token

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=PasswordResetErrorCode.INVALID_TOKEN
        )

    # Validar reset_token JWT
    token_payload = JWTResetService.verify_reset_token(reset_token)

    if not token_payload:
        AuditService.log_suspicious_activity(
            email="unknown",
            ip_address=ip_address,
            activity_type="invalid_reset_token",
            details="Token inválido o expirado",
            user_agent=user_agent
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=PasswordResetErrorCode.TOKEN_EXPIRED
        )

    # Extraer datos del token
    user_id = int(token_payload.get("sub"))  # JWT subject is a string, convert to int
    session_id = token_payload.get("session_id")
    email = token_payload.get("email")

    # Obtener usuario
    user = user_service.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=PasswordResetErrorCode.USER_NOT_FOUND
        )

    # Obtener sesión para validar uso único
    reset_session = CRUDPasswordResetSession.get_by_session_id(db, session_id)
    if not reset_session or reset_session.is_used:
        AuditService.log_suspicious_activity(
            email=email,
            ip_address=ip_address,
            activity_type="reused_token",
            details="Intento de reutilizar reset_token",
            user_agent=user_agent
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=PasswordResetErrorCode.TOKEN_ALREADY_USED
        )

    # Validar nueva contraseña
    is_valid, error_message = password_validator.check_password_reuse(
        new_password=confirm_data.new_password,
        current_hash=user.hashed_password,
        password_history=user.password_history or []
    )

    if not is_valid:
        AuditService.log_password_reset_attempt(
            email=email,
            ip_address=ip_address,
            success=False,
            reason=error_message,
            user_agent=user_agent
        )
        # Detectar si es reuso de contraseña o contraseña inválida
        if "anterior" in error_message.lower() or "reutilizado" in error_message.lower():
            error_code = PasswordResetErrorCode.PASSWORD_REUSED
        else:
            error_code = PasswordResetErrorCode.INVALID_PASSWORD

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_code
        )

    # ✅ Cambiar contraseña
    from app.core.security import get_password_hash

    # Agregar contraseña actual al historial
    user.password_history = password_validator.add_to_history(
        current_hash=user.hashed_password,
        password_history=user.password_history or []
    )

    # Cambiar a nueva contraseña
    user.hashed_password = get_password_hash(confirm_data.new_password)

    # Marcar sesión como usada (uso único)
    CRUDPasswordResetSession.mark_used(db, session_id)

    # Revocar todas las sesiones activas del usuario (forzar re-login)
    from app.auth.models import Session as SessionModel
    db.query(SessionModel).filter(
        SessionModel.user_id == user.id,
        SessionModel.is_active == True
    ).update({"is_active": False})

    db.commit()

    # ✅ Auditoría: Contraseña cambiada exitosamente
    AuditService.log_password_changed(
        user_id=user.id,
        email=user.email,
        ip_address=ip_address,
        user_agent=user_agent,
        method="reset"
    )

    # Limpiar cookies de sesión y reset_token
    response.delete_cookie(
        key="filemeshy_password_reset_session",
        path="/api/v1/auth/password-reset"
    )
    response.delete_cookie(
        key="filemeshy_password_reset_token",
        path="/api/v1/auth/password-reset"
    )

    return SuccessResponse(
        status=200,
        message="Contraseña actualizada exitosamente",
        data={
            "message": "Contraseña actualizada exitosamente"
        }
    )


# ============================================================
# ENDPOINTS DE AUTENTICACIÓN DE DOBLE FACTOR (2FA - TOTP)
# ============================================================

@router.get("/2fa/status", response_model=SuccessResponse)
def get_2fa_status(
    current_user: User = Depends(get_current_active_user),
):
    """Retorna si el usuario tiene 2FA habilitado y cuántos backup codes quedan."""
    backup_remaining = len(current_user.backup_codes or [])
    return SuccessResponse(
        status=200,
        message="Estado 2FA obtenido",
        data=TwoFactorStatus(
            enabled=bool(current_user.totp_enabled),
            backup_codes_remaining=backup_remaining
        ).model_dump()
    )


@router.post("/2fa/setup", response_model=SuccessResponse)
def setup_2fa(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Inicia la configuración de 2FA.
    Genera un secreto TOTP y el QR code. El 2FA NO queda activo hasta llamar /2fa/enable.
    """
    if current_user.totp_enabled:
        # Sin este guard, repetir /2fa/setup con el 2FA ya activo pisaba
        # totp_secret/backup_codes sin confirmar el nuevo con /2fa/enable --
        # el código/backup code viejo (el que el usuario todavía tiene guardado)
        # dejaba de servir y la cuenta quedaba inaccesible hasta encontrar el QR
        # del segundo setup (hallazgo de revisión adversarial, 2026-09-06).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El 2FA ya está activo. Desactivalo primero para volver a configurarlo.",
        )

    secret = TOTPService.generate_secret()
    uri = TOTPService.get_provisioning_uri(secret, current_user.email)
    qr_base64 = TOTPService.generate_qr_base64(uri)
    plain_codes, hashed_codes = TOTPService.generate_backup_codes()

    # Guardar secreto cifrado y backup codes (aún no activado)
    current_user.totp_secret = encrypt_totp_secret(secret)
    current_user.backup_codes = hashed_codes
    db.commit()

    return SuccessResponse(
        status=200,
        message="Configuración 2FA iniciada. Escanea el código QR con tu app autenticadora.",
        data=TwoFactorSetupResponse(
            qr_code=f"data:image/png;base64,{qr_base64}",
            secret=secret,          # Devolver el secreto en texto plano (para mostrar en UI)
            backup_codes=plain_codes
        ).model_dump()
    )


@router.post("/2fa/enable", response_model=SuccessResponse)
def enable_2fa(
    body: TwoFactorVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Activa el 2FA después de verificar que el usuario escaneó el QR correctamente.
    Requiere un código TOTP válido del secreto generado en /2fa/setup.
    """
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primero debes iniciar la configuración en /2fa/setup"
        )

    plain_secret = decrypt_totp_secret(current_user.totp_secret)
    if not TOTPService.verify_code(plain_secret, body.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código incorrecto. Verifica que la hora de tu dispositivo sea correcta."
        )

    current_user.totp_enabled = True
    db.commit()

    return SuccessResponse(
        status=200,
        message="Autenticación de doble factor activada exitosamente",
        data={"enabled": True}
    )


@router.post("/2fa/disable", response_model=SuccessResponse)
def disable_2fa(
    body: TwoFactorDisableRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Desactiva el 2FA. Acepta código TOTP o un backup code.
    """
    if not current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El 2FA no está habilitado"
        )

    plain_secret = decrypt_totp_secret(current_user.totp_secret or "")
    code_valid = TOTPService.verify_code(plain_secret, body.code)

    if not code_valid:
        # Intentar con backup code
        backup_valid, remaining = TOTPService.verify_backup_code(
            body.code, current_user.backup_codes or []
        )
        if backup_valid:
            current_user.backup_codes = remaining
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Código incorrecto. Ingresa un código TOTP o un código de respaldo válido."
            )

    current_user.totp_enabled = False
    current_user.totp_secret = None
    current_user.backup_codes = []
    db.commit()

    return SuccessResponse(
        status=200,
        message="Autenticación de doble factor desactivada",
        data={"enabled": False}
    )


@router.post("/2fa/verify-login", response_model=SuccessResponse)
def verify_2fa_login(
    body: TwoFactorLoginVerify,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Completa el login verificando el código TOTP.
    Recibe el pre_auth_token del paso anterior y retorna los tokens completos.
    """
    ip_address = request.client.host if request.client else "unknown"

    # Validar pre_auth_token PRIMERO -- necesitamos su `jti` (único por sesión
    # de pre-autenticación, generado en /login) para poder armar una clave de
    # rate-limit que aísle a cada sesión de login pendiente.
    payload = decode_token(body.pre_auth_token)
    if not payload or payload.get("type") != "pre_auth":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de pre-autenticación inválido o expirado"
        )

    # Rate limiting por sesión de pre-autenticación (jti) para evitar fuerza
    # bruta de códigos TOTP. ANTES la clave usaba `pre_auth_token[:16]` --
    # los primeros 16 caracteres de CUALQUIER JWT HS256 son siempre el mismo
    # string (el header base64 fijo `{"alg":"HS256","typ":"JWT"}`), así que
    # ese componente de la clave era constante sin importar el usuario/sesión:
    # el límite terminaba siendo compartido por TODAS las sesiones de
    # pre-autenticación detrás de la misma IP (dos usuarios distintos
    # probando códigos en paralelo se bloqueaban entre sí -- DoS, hallazgo de
    # auditoría de seguridad). `jti` sí es único por sesión, así que cada
    # intento de 2FA queda aislado a SU PROPIO login pendiente.
    jti = payload.get("jti")
    rl_key = f"totp:{jti}" if jti else f"totp:{ip_address}:{body.pre_auth_token}"
    is_allowed, rl_message = RateLimiter.check_rate_limit(rl_key)
    if not is_allowed:
        raise HTTPException(status_code=429, detail=rl_message)

    # Pre_auth_token de un solo uso — verificar que el JTI no haya sido consumido
    if jti:
        try:
            from app.core.cache import cache
            if cache.enabled and cache.client:
                jti_key = f"used_pre_auth:{jti}"
                if cache.client.exists(jti_key):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token de pre-autenticación ya utilizado"
                    )
        except HTTPException:
            raise
        except Exception:
            pass  # Si Redis falla, continuar sin la validación de uso único

    email = payload.get("sub")
    user = user_service.get_by_email(db, email=email)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado"
        )

    plain_secret = decrypt_totp_secret(user.totp_secret or "")
    code_valid = TOTPService.verify_code(plain_secret, body.code)

    if not code_valid:
        # Intentar con backup code
        backup_valid, remaining = TOTPService.verify_backup_code(
            body.code, user.backup_codes or []
        )
        if backup_valid:
            user.backup_codes = remaining
            db.commit()
        else:
            RateLimiter.record_attempt(rl_key)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Código incorrecto"
            )

    # Marcar el JTI como consumido en Redis (token de un solo uso)
    if jti:
        try:
            from app.core.cache import cache
            if cache.enabled and cache.client:
                cache.client.setex(f"used_pre_auth:{jti}", 300, "1")  # TTL = 5 min
        except Exception:
            pass  # Si Redis falla, continuar

    # Completar el login generando tokens completos
    user_agent = request.headers.get("user-agent")

    tokens = AuthService.complete_login_after_2fa(db, email=email, ip_address=ip_address, user_agent=user_agent)

    log_audit(
        db=db,
        request=request,
        user_id=str(tokens.user.id),
        user_email=tokens.user.email,
        action="LOGIN",
        table_name="sessions",
        record_id=tokens.user.id,
        new_data={"email": tokens.user.email, "ip": ip_address, "method": "2fa"},
    )

    response.set_cookie(
        key=refresh_cookie_name(0),
        value=tokens.refresh_token,
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax"
    )
    set_csrf_cookie(response, generate_csrf_token())

    login_data = {
        "access_token": tokens.access_token,
        "token_type": "bearer",
        "user": tokens.user.model_dump()
    }
    if _is_desktop_client(request):
        login_data["refresh_token"] = tokens.refresh_token

    return SuccessResponse(
        status=200,
        message="Login exitoso",
        data=login_data
    )

