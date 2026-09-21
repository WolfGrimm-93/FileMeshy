"""
FileMeshy -- Office Converter (Ronda 5)

Servicio HTTP aislado que convierte documentos de Office (docx/xlsx/pptx y
equivalentes) a PDF usando LibreOffice headless como subprocess.

Contrato (consumido por `backend`, ver app/core/config.py::OFFICE_CONVERTER_URL):

    POST /convert   multipart/form-data, campo "file"
        -> 200 application/pdf              bytes del PDF generado
        -> 400 {"detail": "..."}            archivo vacio / extension no soportada
        -> 413 {"detail": "..."}            archivo mas grande que MAX_UPLOAD_BYTES
        -> 422 {"detail": "..."}            LibreOffice no pudo convertir el documento
                                              (corrupto, formato no soportado, etc.)
        -> 504 {"detail": "..."}            timeout de conversion (CONVERT_TIMEOUT_SECONDS)
        -> 500 {"detail": "..."}            error interno inesperado (nunca stack trace crudo)

    GET /health     sin dependencias externas, para healthcheck de Docker.

Modelo de seguridad de este servicio: NO tiene autenticacion propia y NO se
expone al host (sin `ports:` en docker-compose.yml) -- solo es alcanzable
desde el contenedor `backend` a traves de la red interna de Docker, por
nombre de servicio (`http://office_converter:8080`). El aislamiento real
viene del contenedor (no-root, read_only, cap_drop ALL, no-new-privileges,
sin acceso a la red del host) mas el hardening de LibreOffice descripto mas
abajo -- ver Dockerfile y docker-compose.yml para el resto de los controles.
"""

import logging
import os
import shutil
import signal
import subprocess
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s office_converter: %(message)s",
)
logger = logging.getLogger("office_converter")

app = FastAPI(
    title="FileMeshy Office Converter",
    # Sin docs publicas -- este servicio no deberia ser explorado por nadie
    # mas que `backend`, y no tiene sentido exponer Swagger/Redoc en un
    # servicio interno sin auth.
    docs_url=None,
    redoc_url=None,
)

# --- Configuracion --------------------------------------------------------

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
CONVERT_TIMEOUT_SECONDS = 30
TMP_ROOT = Path("/tmp")
PROFILE_SEED = Path("/opt/lo_profile_seed/user")
SOFFICE_BIN = shutil.which("soffice") or shutil.which("libreoffice") or "/usr/bin/soffice"

# Solo para devolver un 400 rapido y un mensaje claro antes de gastar un
# proceso de conversion completo -- NO es un control de seguridad: la
# extension declarada por el cliente no dice nada de lo que hay realmente
# adentro del archivo, y LibreOffice detecta el formato por contenido. La
# seguridad real contra un archivo malicioso disfrazado de .docx es el
# aislamiento del contenedor + el hardening de macros/enlaces del perfil de
# LibreOffice (ver lo_hardening/registrymodifications.xcu), no este filtro.
ALLOWED_EXTENSIONS = {
    ".doc", ".docx", ".dot", ".dotx", ".odt", ".ott", ".rtf",
    ".xls", ".xlsx", ".xlt", ".xltx", ".ods", ".ots", ".csv",
    ".ppt", ".pptx", ".pot", ".potx", ".odp", ".otp",
}


# --- Utilidades internas ---------------------------------------------------


def _reject(status_code: int, detail: str) -> None:
    raise HTTPException(status_code=status_code, detail=detail)


def _kill_process_group(proc: subprocess.Popen) -> None:
    """Mata el grupo de procesos completo, no solo el wrapper `soffice`.

    `soffice` es un lanzador delgado que hace fork de `soffice.bin`; si solo
    matamos el PID del wrapper (lo que hace un `proc.kill()` simple o el
    timeout de `subprocess.run`), el proceso real que esta parseando el
    documento puede sobrevivir colgado, acumulandose contenedor tras
    contenedor. Lanzamos el proceso con `start_new_session=True` (su propio
    process group) precisamente para poder matar todo el arbol aca con
    `os.killpg`.
    """
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def _run_soffice(cmd: list[str], timeout: int, home_dir: Path) -> tuple[int, bytes, bytes]:
    """Corre soffice con timeout duro y kill de todo el process group.

    `home_dir` se pasa como $HOME del subprocess -- con `read_only: true` y
    solo `/tmp` como tmpfs (ver docker-compose.yml), el $HOME real
    (/home/appuser) queda de solo lectura, y LibreOffice intenta escribir
    ahi cache de dconf/fontconfig en cada arranque. Sin este HOME
    redirigido, la conversion igual funciona (LibreOffice tolera el fallo
    y sigue), pero llena stderr de errores de "Read-only file system" en
    cada request y recalcula caches que podria haber reusado. `home_dir`
    vive dentro del mismo directorio de trabajo efimero de esta conversion
    (bajo /tmp, tmpfs), asi que queda escribible y se limpia solo al final.

    Devuelve (returncode, stdout, stderr). Lanza subprocess.TimeoutExpired
    si se excede el timeout (ya despues de haber matado el proceso).
    """
    env = dict(os.environ)
    env["HOME"] = str(home_dir)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        env=env,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        # Drenar pipes para no dejar el proceso zombie/bloqueado.
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        raise
    return proc.returncode, stdout, stderr


def _new_lo_profile_dir(work_dir: Path) -> Path:
    """Copia el perfil semilla (macros deshabilitadas, ver Dockerfile) a un
    directorio efimero nuevo para esta conversion. Nunca se reutiliza un
    perfil entre requests -- LibreOffice ademas no tolera dos instancias
    compartiendo el mismo perfil concurrentemente (lock file)."""
    profile_dir = work_dir / "lo_profile"
    dest_user_dir = profile_dir / "user"
    dest_user_dir.parent.mkdir(parents=True, exist_ok=True)
    if PROFILE_SEED.exists():
        shutil.copytree(PROFILE_SEED, dest_user_dir)
    else:  # pragma: no cover - solo si el build no copio la semilla
        dest_user_dir.mkdir(parents=True, exist_ok=True)
        logger.warning(
            "No se encontro el perfil semilla en %s -- corriendo con perfil "
            "default de LibreOffice (macros posiblemente NO deshabilitadas)",
            PROFILE_SEED,
        )
    return profile_dir


# --- Endpoints ---------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    """Healthcheck liviano -- no invoca soffice a proposito (un healthcheck
    que lanza un proceso de LibreOffice cada pocos segundos seria un
    generador de carga/ruido en si mismo). Solo confirma que el proceso
    uvicorn esta vivo y respondiendo."""
    return {"status": "ok"}


@app.post("/convert")
async def convert(request: Request, file: UploadFile = File(...)) -> Response:
    original_name = Path(file.filename or "documento").name  # sin paths
    suffix = Path(original_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        _reject(
            400,
            f"Extension '{suffix or '(sin extension)'}' no soportada para "
            f"conversion a PDF.",
        )

    # Rechazo temprano por Content-Length si el cliente lo declaro (no es
    # confiable al 100% -- igual se refuerza mas abajo con una lectura
    # acotada del cuerpo real).
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_UPLOAD_BYTES:
                _reject(
                    413,
                    f"Archivo demasiado grande (declarado {content_length} "
                    f"bytes, limite {MAX_UPLOAD_BYTES} bytes).",
                )
        except ValueError:
            pass

    # Lectura acotada: pedimos como maximo MAX_UPLOAD_BYTES + 1 bytes, sin
    # importar lo que haya dicho Content-Length (que el cliente puede
    # omitir u omitir a proposito con Transfer-Encoding: chunked). Esto
    # evita cargar en memoria un archivo arbitrariamente grande solo para
    # despues rechazarlo.
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()

    if len(data) == 0:
        _reject(400, "El archivo enviado esta vacio.")
    if len(data) > MAX_UPLOAD_BYTES:
        _reject(
            413,
            f"Archivo demasiado grande (limite {MAX_UPLOAD_BYTES} bytes).",
        )

    work_dir = Path(tempfile.mkdtemp(prefix="office_conv_", dir=str(TMP_ROOT)))
    try:
        in_dir = work_dir / "in"
        out_dir = work_dir / "out"
        in_dir.mkdir()
        out_dir.mkdir()

        # Nombre de archivo generado por nosotros (no el que mando el
        # cliente) -- evita cualquier sorpresa con nombres raros/unicode al
        # armar la ruta de salida, pero conserva la extension original
        # porque LibreOffice la usa como pista de formato de entrada.
        stem = uuid.uuid4().hex
        input_path = in_dir / f"{stem}{suffix}"
        input_path.write_bytes(data)

        profile_dir = _new_lo_profile_dir(work_dir)
        home_dir = work_dir / "home"
        home_dir.mkdir()

        cmd = [
            SOFFICE_BIN,
            f"-env:UserInstallation=file://{profile_dir}",
            "--headless",
            "--invisible",
            "--nologo",
            "--nofirststartwizard",
            "--norestore",
            "--nolockcheck",
            "--nodefault",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(input_path),
        ]

        logger.info("Convirtiendo %s (%d bytes)", original_name, len(data))

        try:
            returncode, stdout, stderr = _run_soffice(cmd, CONVERT_TIMEOUT_SECONDS, home_dir)
        except subprocess.TimeoutExpired:
            logger.warning(
                "Timeout (%ss) convirtiendo %s -- proceso soffice matado",
                CONVERT_TIMEOUT_SECONDS,
                original_name,
            )
            _reject(
                504,
                f"La conversion excedio el limite de {CONVERT_TIMEOUT_SECONDS}s.",
            )

        if returncode != 0:
            logger.warning(
                "soffice salio con codigo %s para %s. stderr=%r",
                returncode,
                original_name,
                stderr[-2000:],
            )
            _reject(
                422,
                "No se pudo convertir el documento (formato no soportado o "
                "archivo corrupto).",
            )

        output_path = out_dir / f"{stem}.pdf"
        if not output_path.exists():
            logger.warning(
                "soffice devolvio codigo 0 pero no genero PDF para %s. "
                "stdout=%r stderr=%r",
                original_name,
                stdout[-1000:],
                stderr[-1000:],
            )
            _reject(422, "La conversion no genero un PDF de salida.")

        pdf_bytes = output_path.read_bytes()
        if not pdf_bytes.startswith(b"%PDF-"):
            logger.error(
                "Salida para %s no tiene firma %%PDF- (primeros bytes: %r)",
                original_name,
                pdf_bytes[:16],
            )
            _reject(500, "La conversion produjo un archivo invalido.")

        return Response(content=pdf_bytes, media_type="application/pdf")

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error inesperado convirtiendo %s", original_name)
        _reject(500, "Error interno al convertir el documento.")
    finally:
        # Limpieza SIEMPRE, exito o error -- input, output y perfil de
        # LibreOffice efimero, para no acumular basura en el tmpfs de /tmp.
        shutil.rmtree(work_dir, ignore_errors=True)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Red de seguridad final: cualquier excepcion no capturada explicitamente
    arriba nunca debe devolver un stack trace crudo al cliente."""
    logger.exception("Excepcion no manejada: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor."})
