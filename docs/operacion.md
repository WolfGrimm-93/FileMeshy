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

`backend` y `celery_worker` comparten build Y tag de imagen (`image: filemeshy-backend`, ancla `x-backend-build` en `docker-compose.yml`): reconstruir cualquiera de los dos actualiza la misma imagen, así el worker no puede quedar desfasado. (Incidente de la Ronda 12: cuando cada servicio tenía su propia imagen, `docker compose build backend` NO reconstruía la del worker, que estuvo corriendo con dependencias viejas mientras se creía lo contrario.) `office_converter` sigue teniendo imagen propia y se reconstruye aparte. Secuencial, un comando docker a la vez:

```
docker compose build backend
docker compose up -d --force-recreate backend celery_worker
```

**Verificación obligatoria tras cada deploy** (los dos comandos deben dar IDs idénticos y el mismo md5):

```
docker inspect --format '{{.Name}} {{.Image}}' filemeshy-backend-1 filemeshy-celery_worker-1
for s in backend celery_worker; do docker compose exec -T $s pip freeze | md5sum; done
```

En producción (`docker-compose.prod.yml`, no versionado) aplicar el mismo cambio a mano: ancla de build compartida y `image:` idéntico en ambos servicios, o repetir el chequeo de arriba en cada despliegue.

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

## 6. Verificación del primer arranque del compose nuevo (HECHA en dev)

Backend y celery_worker ahora dependen de que minio esté `healthy` vía `mc ready local`. Confirmar que la imagen pinneada trae `mc`:

```
docker run --rm --entrypoint mc quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z --version
```

Si no lo trae, minio quedará `unhealthy` y bloqueará backend y worker. **Verificado el 2026-09-25:** la imagen pinneada trae `mc` (`mc version RELEASE.2025-08-13T08-35-41Z`) y los 8 servicios llegan a `healthy` en el arranque en frío. Repetir el chequeo si se cambia el digest de MinIO.

## 7. Deuda de dependencias conocida

Medido con pip-audit (`--no-deps --disable-pip -r`, sobre los requirements y, desde la Ronda 12, también sobre el `pip freeze` real de las imágenes reconstruidas, que sí cubre transitivas) y `pnpm audit --prod`.

### Resuelto en la Ronda 12 (backend y office_converter)

| Paquete | Antes | Ahora | Vulns antes |
|---|---|---|---|
| pypdf (backend) | 4.3.1 | 6.19.0 | 77 |
| pillow (backend) | 11.0.0 | 12.3.0 | 33 |
| python-multipart (backend y office_converter) | 0.0.18 | 0.0.32 | 12 c/u |
| python-dotenv (backend) | 1.0.0 | 1.2.3 | 2 |
| pymysql (backend) | 1.1.0 | eliminado (sin usos) | 2 |
| starlette (backend y office_converter, antes transitiva) | 0.41.3 | 1.3.1 (pin explícito) | 14 |
| fastapi | 0.115.6 | 0.135.3 | (arrastraba starlette<0.42) |
| pydantic / pydantic-settings | 2.5.2 / 2.1.0 | 2.12.5 / 2.10.1 | (requisito de fastapi 0.135) |

También se quitaron del requirements del backend paquetes sin ningún uso en `app/`, `tests/`, `scripts/`, migraciones ni compose: sqlmodel, faker, pandas, schedule, flower.

Resultado: pip-audit sobre el `pip freeze` real de backend (76 paquetes) y de office_converter (20): 0 vulnerabilidades conocidas; la API JSON de PyPI (`vulnerabilities`) de cada versión instalada también da 0. Antes: 126 en los pines directos del backend + 14 de starlette transitivo (~140), y 12 + 14 en el conversor.

Cambios de comportamiento a tener presentes:
- python-multipart >= 0.0.30 ya no interpreta `filename*=UTF-8''...` (RFC 2231) en multipart/form-data: esa parte deja de tratarse como archivo (respuesta 4xx limpia). Los navegadores y httpx envían `filename="..."` en UTF-8 crudo, que sigue funcionando (test `test_multipart_unicode_avatar.py`).
- `@app.on_event` se migró a `lifespan` (Starlette 1.0 lo elimina); canario en `tests/test_app_canaries.py`.
- Las constantes `HTTP_413_REQUEST_ENTITY_TOO_LARGE` / `HTTP_422_UNPROCESSABLE_ENTITY` están deprecadas en Starlette 1.x (solo warning); migrar a `*_CONTENT_TOO_LARGE` / `*_UNPROCESSABLE_CONTENT` en una ronda futura.
- Los ~29 patrones legacy de pydantic v1 (`class Config`, `.dict()`, `@validator`, `from_orm`) siguen funcionando en pydantic 2.12 y solo emiten deprecation warnings; migrarlos antes de pydantic 3.

### Fase 4 de la Ronda 12 (correcciones tras la revisión adversarial)

- **`celery_worker` y `backend` ahora comparten imagen** (ver §4). Antes cada servicio tenía la suya y el worker quedó con las dependencias viejas sin que nada lo avisara; se detectó con `pip freeze` de cada contenedor.
- **Enmascarado de secretos de configuración**: `GET /admin/config/email`, `/admin/config/all` y `/admin/config/category/{c}` devuelven `"****"` para cualquier fila con `is_encrypted=true` O cuya `config_key` termine en `password`, `secret`, `secret_key`, `api_key`, `private_key` o `token` (sufijo, no subcadena: `password_min_length` es una política y se muestra). Valores `false`/`0` ya no se devuelven como `null`.
- **Recorte de User-Agent/IP**: `sessions.user_agent` (500) y `sessions.ip_address` (45) se recortan al guardar (`Session.clip_user_agent` + validadores del modelo); el UA vacío se guarda como `unknown`. Antes, un UA de 600+ caracteres daba 500 en el login. El audit log recorta `action`(20), `table_name`(100), `record_id`(100), `ip_address`(45), `endpoint`(255) y `method`(10).
- **`POST /roles`**: `permission_ids` admite como máximo 1000 ids (422 si excede); rechaza ids inexistentes o de permisos inactivos con 422 (el detalle lista como máximo 20 ids y "y N más"); una carrera por nombre duplicado responde 409 en vez de 500. `PUT /roles/{id}/permissions` no cambió (no valida existentes/activos de esta forma).
- **`scripts/reindex_legacy_pending.py --all-schemas`** recorre todos los tenants activos (`iter_tenant_schemas()`; en modo local equivale al schema por defecto). Sin `--all-schemas` ni `--schema`, en modo cloud solo procesa `public`.
- Los tests de pytest que promueven usuarios a ADMIN/SUPER_ADMIN los bajan a USER y los desactivan al terminar (fixture autouse `_demote_privileged_users` en `tests/conftest.py`).

### Fase 5 de la Ronda 12 (cierre tras la auditoría final)

- **Secretos de configuración cifrados al guardar** en TODOS los caminos (antes solo `PUT /admin/config/email` cifraba, y `POST /admin/config/smtp`, `PUT /admin/config/turnstile`, `POST /admin/config/create` y `PUT /admin/config/update/{key}` los dejaban en claro aunque decían cifrarlos). Se usa el mismo Fernet de `app/core/security.py` (`encrypt_secret_if_needed`, idempotente). Los consumidores (envío de email, Turnstile) descifran con `decrypt_secret_tolerant`, que acepta valores legados en claro: NADA se rompe en instalaciones existentes, y un secreto en claro se cifra la próxima vez que se guarde. No hay migración masiva: los secretos ya guardados en claro siguen así hasta re-guardarse.
- El enmascarado devuelve `"****"` solo si el secreto tiene valor; si está vacío devuelve `null` (el estado mostrado es honesto). Un `"****"` reenviado por un cliente ya no sobreescribe el secreto guardado.
- Los logs de auditoría de auth pasan el UA/IP/email por `sanitize_for_log` (caracteres de control fuera, truncado a 200).
- Constantes deprecadas de Starlette migradas (`HTTP_413_CONTENT_TOO_LARGE`, `HTTP_422_UNPROCESSABLE_CONTENT`, y también 414/416).
- Datos de prueba: las filas legadas de `file_content_index` en 'pending' sin `attempted_at` las creaban los tests de `test_reindex_legacy_pending.py` (no un camino real de código); ahora se limpian solas. `scripts/reindex_legacy_pending.py` se ejecutó una vez sobre el stack de desarrollo (32 filas → 0).
- **CI:** `eslint`, `tsc` y `sca` ya son bloqueantes (0 errores, 0 warnings, 0 vulnerabilidades). Nuevo job `backend-tests`, con `continue-on-error: true` hasta la primera corrida verde en un runner real (no verificado).

## 8. Cambios de contrato de la Ronda 12 (backend↔frontend)

- **Fechas:** toda respuesta que use `SuccessResponse`/`to_utc_iso` devuelve ISO 8601 con sufijo `Z`
  (antes algunos endpoints devolvían `+00:00Z`, inválido, y el frontend mostraba fechas vacías o
  "Invalid Date"). El frontend además tolera ambos formatos (`shared/utils/dates.ts::parseDate`) por
  si algún dato legado o de un consumidor externo llega distinto.
- **Avatar:** el único camino para SUBIR un avatar es `POST /users/{id}/avatar` (multipart, campo
  `file`, jpeg/png/webp/gif, máximo 5 MB, cualquier usuario sobre su propia foto o con
  `users.edit`/`admin.manage` sobre otra). `PUT /users/{id}` con el campo `avatar` **solo** acepta
  `null`, `""` o el valor actual ya guardado — cualquier otro valor (base64, data-URI, una clave de
  storage ajena) da 422. Es un cambio de contrato: un cliente viejo que mandara el avatar por `PUT`
  deja de funcionar a propósito (era la causa de un IDOR real, ver pendiente.md Ronda 12).
- **Copiar:** `POST /files/{id}/copy` y `POST /folders/{id}/copy` — sin `folder_id` ni `to_root` en
  el body (o body vacío) copia en la MISMA carpeta del original; `folder_id: "<uuid>"` copia ahí;
  `to_root: true` (o, por compatibilidad, `folder_id: null` explícito) copia en la raíz. `to_root:
  true` junto con un `folder_id` no nulo da 422. Copiar un archivo/carpeta desde/hacia un descendiente
  de sí mismo da 400. La copia ahora es server-side en MinIO (antes leía el archivo completo a
  memoria del backend).
- **Riesgo de despliegue — CSP y avatar/preview en producción:** `filemeshy_front/nginx.conf` fija
  `img-src`/`media-src`/`frame-src` a `'self' data: http://localhost:58102` (el puerto de MinIO en
  dev). Si en producción `MINIO_PUBLIC_URL` NO queda en el mismo origen que el frontend, los avatares
  y los previews de imagen/video/PDF quedarán bloqueados por la CSP sin ningún error de red visible
  (solo la violación en la consola del navegador) — agregar el origen real de MinIO a esas
  directivas al desplegar, o confirmar que `MINIO_PUBLIC_URL` es same-origin (ver Ronda 5 en
  pendiente.md, ya documentado ahí para el caso general de previews).

### Sigue pendiente

- **Frontend:** `pnpm audit` y `pnpm audit --prod` dan 0 vulnerabilidades (react-router 7.18.4). Ya no hay deuda de dependencias conocida en el frontend.
- **Backend:** el `pip-audit` de CI usa `--no-deps --disable-pip` (no cubre transitivas). Las transitivas sí se auditaron con el `pip freeze` real de las imágenes (0). Falta auditar con resolución completa en un runner con Python 3.11 (en el host con Python 3.14 falla al compilar `psycopg2-binary`).
- Pines sin subir a propósito (sin CVEs reportados por PyPI/pip-audit): uvicorn 0.32.1, httpx 0.25.2 (el `TestClient` de Starlette 1.x pide httpx >= 0.27; los tests usan `httpx.Client` contra el servidor real, no `TestClient`) y celery 5.3.6.
- Patrones legacy de pydantic v1 (`class Config`, `.dict()`, `@validator`, `from_orm`): solo dan deprecation warnings; migrarlos antes de pydantic 3.
- `passlib 1.7.4` sin mantenimiento (compatibilidad con bcrypt fijada a propósito).
