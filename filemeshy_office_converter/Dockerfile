# FileMeshy -- Office Converter (Ronda 5)
#
# Servicio aislado de conversion Office -> PDF via LibreOffice headless.
# Motivo del aislamiento: Nextcloud/Seafile embeben LibreOffice headless
# para esto, pero ownCloud lo marca directamente "unsupported" corriendolo
# sin aislar -- hay CVE de RCE reales al parsear documentos maliciosos
# (CVE-2024-12425/12426, CVE-2025-0514, CVE-2025-1080). La mitigacion
# estandar de la industria es exactamente lo que hace este Dockerfile +
# docker-compose.yml: contenedor separado, sin red de entrada, no-root,
# sin privilegios, sin macros, con limites de recursos.
#
# Base: debian:bookworm-slim (no python:3.11-slim) -- instalar LibreOffice
# de apt encima de bookworm-slim es mas liviano que instalar todo el arbol
# de dependencias de LibreOffice encima de una imagen basada en Python;
# Python se instala aparte, es la parte chica.
#
# Version de LibreOffice: Debian bookworm trae LibreOffice 7.4.x, pero
# backportea fixes de seguridad a esa MISMA linea de version en vez de
# saltar de version mayor -- confirmado en el Debian Security Tracker: los
# 4 CVE citados arriba estan fijados en 4:7.4.7-1+deb12u6 (12425/12426) y
# 4:7.4.7-1+deb12u7 (2025-1080); 2025-0514 forma parte del mismo aviso
# (DSA-5846-1). Esto SOLO es cierto si el build corre `apt-get update` con
# cache fresca -- si esta imagen se reconstruye desde una capa de Docker
# vieja/cacheada sin `--no-cache`, puede quedar con paquetes desactualizados
# aunque el Dockerfile no haya cambiado. Ver PENDIENTES.md: reconstruir este
# servicio con `--no-cache` (o `--pull`) periodicamente, no solo cuando
# cambia el codigo.
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

# Paquetes de LibreOffice acotados a Writer/Calc/Impress (cubren
# docx/xlsx/pptx y sus equivalentes ODF/legacy) en vez de la metapaquete
# `libreoffice` completa, que arrastra un escritorio grafico entero
# (evolution-data-server, gnome-*, etc.) sin ningun uso para un conversor
# headless -- superficie de ataque y tamano de imagen innecesarios.
#
# fonts-liberation: fuentes metric-compatibles con Arial/Times New
# Roman/Courier New -- sin esto, documentos .docx que usan esas fuentes
# (la enorme mayoria generados por MS Office) se sustituyen por una fuente
# generica fea al renderizar el PDF.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        libreoffice-calc \
        libreoffice-impress \
        libreoffice-core \
        fonts-liberation \
        python3 \
        python3-venv \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Debian bookworm bloquea `pip install` fuera de un venv (PEP 668,
# "externally-managed-environment") -- usamos un venv en vez de
# --break-system-packages para no pelear contra esa proteccion.
RUN python3 -m venv /opt/venv
COPY requirements.txt .
RUN pip install --no-cache-dir --retries 5 --timeout 60 -r requirements.txt

COPY server.py .

# Perfil de LibreOffice "semilla": macros deshabilitadas al maximo +
# actualizacion de enlaces externos desactivada (ver
# lo_hardening/registrymodifications.xcu para el detalle y las referencias).
# server.py copia este directorio a un perfil efimero nuevo en CADA
# conversion -- este de aca nunca se usa directamente ni se escribe.
COPY lo_hardening/registrymodifications.xcu /opt/lo_profile_seed/user/registrymodifications.xcu

# Usuario no-root desde el arranque -- mismo patron que
# filemeshy_back/Dockerfile: si un documento malicioso explota un bug de
# parseo de LibreOffice (los CVE citados arriba son ejemplos reales de esa
# clase), el atacante queda como maximo con el uid de este usuario sin
# privilegios, sin shell (`nologin`), dentro de un contenedor sin
# capabilities (`cap_drop: [ALL]` en compose) y sin salida a la red del
# host. `chown` ANTES de `USER` -- appuser necesita escribir en /opt para
# que exista /home/appuser (perfil HOME de fallback de LibreOffice) y en
# /tmp en runtime (queda como tmpfs por `read_only: true` en compose).
RUN useradd -m -u 1000 -s /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app /opt/lo_profile_seed /home/appuser

USER appuser

EXPOSE 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
