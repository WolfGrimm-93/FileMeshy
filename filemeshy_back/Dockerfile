FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
# libvips-dev: requerido por pyvips (compresion/redimensionado de imagenes subidas)
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libvips-dev \
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
