# Pin por DIGEST (Ronda 10) -- "3.11-slim" es una tag flotante (patches de
# Python 3.11.x + base Debian que se actualizan sin aviso en cualquier
# rebuild). Python 3.11.16 confirmado en vivo con `python3 --version`
# corriendo la imagen real, digest vigente al 2026-09-22.
FROM python:3.11-slim@sha256:da047cb8f9d1d98e5c070f5300ba9f7274e33b8fc0e5be5ed88740aed1b95ba9

WORKDIR /app

# Instalar dependencias del sistema
# libvips-dev: requerido por pyvips (compresion/redimensionado de imagenes subidas)
# tesseract-ocr + tesseract-ocr-spa: motor de OCR (Ronda 6: busqueda por
#   contenido + OCR) -- paquete de idioma espanol explicito ademas del
#   ingles que ya trae el paquete base, ver TESSERACT_LANGS en
#   app/worker/tasks/indexing.py.
# poppler-utils: requerido por pdf2image para renderizar paginas de PDF a
#   imagenes antes de pasarlas a Tesseract (fallback de OCR sobre PDFs
#   escaneados, ver app/worker/tasks/indexing.py::_ocr_pdf).
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libvips-dev \
    tesseract-ocr \
    tesseract-ocr-spa \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir --retries 5 --timeout 60 -r requirements.txt

# Copiar codigo de la aplicacion
COPY . .

# Usuario no-root -- antes el proceso (alembic + uvicorn) corria como root
# dentro del contenedor sin ningun beneficio real (hallazgo de auditoria de
# seguridad): un RCE en cualquier dependencia (ej. libvips/pyvips procesando
# una imagen subida por un usuario) le daria a un atacante control root
# DENTRO del contenedor de entrada. `chown -R` ANTES de `USER appuser` --
# app_logger (app/core/logging_config.py) crea ./logs/*.log en runtime
# relativo al WORKDIR, asi que appuser necesita poder escribir ahi (en
# docker-compose, esa carpeta ademas queda montada como tmpfs por el
# `read_only: true` del servicio backend).
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Ejecutar migraciones y iniciar servidor
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
