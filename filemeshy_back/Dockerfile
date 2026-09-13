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

EXPOSE 8000

# Ejecutar migraciones y iniciar servidor
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
