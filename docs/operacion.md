# Operación de FileMeshy (runbook mínimo)

## 1. Verificar salud

Todos los servicios de `docker-compose.yml` tienen healthcheck:

| Servicio | Chequeo | Intervalo / start_period |
|---|---|---|
| postgres, redis | `pg_isready` / `redis-cli ping` | 5s |
| minio | `mc ready local` | 10s / 10s |
| backend | GET `/health` interno (valida `status == healthy`) | 30s / 60s |
| celery_worker | `celery inspect ping` al propio worker | 60s / 40s |
| office_converter | GET `/health` en :8080 | 30s / 20s |
| clamav | `clamdcheck.sh` | 30s / 900s |
| frontend | `wget --spider http://127.0.0.1/` | 30s / 10s |

```
docker compose ps                      # columna STATUS: healthy / unhealthy
docker inspect --format '{{json .State.Health}}' <contenedor>   # detalle del último chequeo
```

El frontend arranca con `service_started` sobre backend (a propósito: backend espera a clamav hasta 15 min en el primer arranque).

## 2. Actualizar digests pinneados

Cuándo: mensualmente, o ante un CVE en la imagen base. Dependabot (`.github/dependabot.yml`) propone los PR de imágenes.

```
docker buildx imagetools inspect postgres:15.19-alpine      # línea "Digest:" (índice multi-arch)
# alternativa: docker manifest inspect <imagen:tag> (requiere leer el digest del índice)
```

Reemplazar el `@sha256:...` en `docker-compose.yml` o en el `FROM` del Dockerfile correspondiente, y actualizar el comentario con la fecha y la versión confirmada.

`office_converter` instala LibreOffice con apt: reconstruir con caché fresca de forma periódica, no solo al cambiar código:

```
docker compose build --no-cache --pull office_converter
```

## 3. Verificar que freshclam sale por `clamav_egress`

`clamav` está en `av_net` (internal) + `clamav_egress` (bridge). Tras levantar el stack:

```
docker compose exec clamav freshclam
docker compose logs clamav | grep -i freshclam
docker compose exec clamav ip route      # debe haber default via el gateway de clamav_egress
```

Si falla por red, revisar la ruta por defecto del contenedor (la trampa de los contenedores multi-red). Verificar también que `office_converter` NO tiene salida (`docker compose exec office_converter python3 -c "import urllib.request;urllib.request.urlopen('http://example.com',timeout=5)"` debe fallar).

## 4. Orden de rebuild backend + celery_worker

Ambos usan la misma imagen (`./filemeshy_back`). Secuencial, un comando docker a la vez:

```
docker compose build backend
docker compose build celery_worker
docker compose up -d backend celery_worker
```

El backend corre `alembic upgrade head` al arrancar: levantar backend primero y esperar a que esté `healthy` antes de dejar que el worker procese con un esquema viejo.

## 4b. Dev: el worker corre SIN `--beat`

El `celery_worker` del `docker-compose.yml` (dev) no lleva `--beat`, así que las tareas periódicas NO corren en dev. Eso incluye `sweep_stale_pending_content_index`, que marca `failed` las filas de indexación `pending` huérfanas tras un worker muerto. En prod sí corren (`docker-compose.prod.yml` usa `--beat`). Para dispararla a mano en dev (nombre real leído de `app/worker/tasks/maintenance.py`; no ejecutado al documentarlo):

```
docker compose exec celery_worker celery -A app.worker.celery_app call app.worker.tasks.maintenance.sweep_stale_pending_content_index
```

## 5. Producción (`docker-compose.prod.yml`, NO versionado)

Ese archivo es el real del servidor y está en `.gitignore`: aplicar estos cambios A MANO, con confirmación previa (requiere `docker compose up`/restart en producción). Nada de esto está aplicado.

### 5.1 Healthchecks

Copiar del `docker-compose.yml` los healthchecks de `backend`, `celery_worker`, `office_converter` y `frontend` (minio y clamav ya lo tienen en prod). Cambiar `depends_on` de backend a `office_converter: service_healthy` y de backend/celery_worker a `minio: service_healthy`.

### 5.2 Redes internas

En prod hoy todo vive en `internal`. Agregar:

```yaml
networks:
  internal:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/24
  av_net:
    internal: true
  converter_net:
    internal: true
  clamav_egress:
    driver: bridge
  proxy:
    external: true
```

- `clamav`: `networks: [av_net, clamav_egress]` (sale de `internal`).
- `office_converter`: `networks: [converter_net]`.
- `backend`: `[internal, av_net, converter_net]`; `celery_worker`: `[internal, av_net]`.
- `frontend`: se queda en `internal` + `proxy`.

### 5.3 TRUSTED_PROXY_IPS y TRUSTED_PROXY_IP_HEADERS

Hoy `TRUSTED_PROXY_IPS` es `"[]"`. Con la subred fija de 5.2, cuando se quiera confiar en el proxy:

- Opción simple: `TRUSTED_PROXY_IPS: '["172.28.0.0/24"]'`.
- Mejor: darle al frontend `ipv4_address: 172.28.0.10` en `internal` y usar `'["172.28.0.10/32"]'`.

Reglas del validator (backend):
- `TRUSTED_PROXY_IPS` acepta IPs sueltas y CIDR.
- Rechaza prefijo 0 (`0.0.0.0/0`, `::/0`).
- Una entrada inválida hace fallar el arranque (intencional, no es un bug).
- El rate-limit por IP de shares públicos normaliza IPv6 a /64.

Nuevo setting `TRUSTED_PROXY_IP_HEADERS`: lista JSON, default `["x-real-ip"]`, valores permitidos `"x-real-ip"` y `"cf-connecting-ip"`, en orden de preferencia. CAMBIO DE COMPORTAMIENTO: antes se prefería siempre `cf-connecting-ip`; ahora es OPT-IN, porque `nginx.conf` solo pisa `X-Real-IP` y un cliente podía falsificar `CF-Connecting-IP`.

(a) Con el default, en prod el rate-limit de shares públicos y la auditoría ven la IP que nginx ponga en `X-Real-IP` (`$remote_addr` = IP de Traefik). Todos los visitantes comparten cupo hasta que se decida (b).

(b) DECISIÓN PENDIENTE DEL USUARIO. Para IP real por visitante hay dos caminos (no se tocó `nginx.conf`):
1. nginx con `set_real_ip_from <CIDR de Traefik>` + `real_ip_header CF-Connecting-IP` (o `X-Forwarded-For` con `real_ip_recursive on`), así `$remote_addr` ya es el visitante y `X-Real-IP` lo refleja.
2. Habilitar `"cf-connecting-ip"` en `TRUSTED_PROXY_IP_HEADERS` SOLO si el tráfico entra únicamente vía Cloudflare y el proxy/nginx pisa ese header cuando no viene de Cloudflare.

### 5.3b Orden de despliegue

1. Reconstruir backend y celery_worker con la MISMA imagen (mismo build de `./filemeshy_back`).
2. Levantar primero el backend y esperar a `healthy`: corre `alembic upgrade head` (migraciones nuevas `e5a1c7d3b9f2` y `f2b8d4e6a1c3`).
3. Recién entonces levantar/permitir que el worker procese, para que no trabaje con un esquema viejo.

Un `TRUSTED_PROXY_IPS` inválido o con prefijo /0 hace fallar el arranque de AMBOS (backend y worker): validar el valor antes de desplegar.

### 5.4 Límite de memoria de celery_worker

Sin límite hoy (OCR/indexación puede crecer). Punto de partida, NO medido: `mem_limit: 2g`. Medir con `docker stats filemeshy-celery-worker` durante indexación/OCR real y ajustar.

### 5.5 Nomenclatura de contenedores (PENDIENTE, requiere confirmación)

Los contenedores de prod se llaman `filemeshy-postgres`, `filemeshy-backend`, etc. La nomenclatura obligatoria es `filemeshy-prod-<servicio>` (p. ej. `filemeshy-prod-celery-worker`). Renombrar recrea los contenedores: queda PENDIENTE hasta que el usuario lo confirme. Ídem para dev (`docker-compose.yml` no fija `container_name`; el prefijo lo da el nombre del proyecto).

## 6. Verificación pendiente en el primer arranque del compose nuevo

Backend y celery_worker ahora dependen de que minio esté `healthy` vía `mc ready local`. Confirmar que la imagen pinneada trae `mc`:

```
docker run --rm --entrypoint mc quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z --version
```

Si no lo trae, minio quedará `unhealthy` y bloqueará backend y worker. (Se verifica en la fase de Build; no verificado al escribir esto.)

## 7. Deuda de dependencias conocida

Medido con pip-audit (backend con `--no-deps --disable-pip`, sin cubrir transitivas) y `pnpm audit --prod`. Revisar hasta que se actualicen:

| Paquete | Versión actual | Vulns | Fix |
|---|---|---|---|
| pypdf (backend) | 4.3.1 | 77 | 6.9.2 |
| pillow (backend) | 11.0.0 | 33 | 12.3.0 |
| python-multipart (backend y office_converter) | 0.0.18 | 12 c/u | 0.0.31 |
| python-dotenv (backend) | 1.0.0 | 2 | 1.2.2 |
| pymysql (backend) | 1.1.0 | 2 | 1.1.1 |
| starlette (office_converter, transitiva) | 0.41.3 | varias | hasta 1.3.1 |
| react-router (front, vía react-router-dom) | <7.18.2 | 5 (2 altas, 3 moderadas) | >=7.18.2 |

Total backend: 126 vulnerabilidades en 5 paquetes. El job `sca` de CI es `continue-on-error` por esto: quitarlo cuando se actualice.
