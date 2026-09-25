# Pendientes

Lista de lo que falta o quedó sin resolver — se saca de acá en cuanto se resuelve. Arranca
vacía a partir de 2026-09-12 (reinicio del proyecto).

## Auditoría 2026-09-19 + Ronda 1 de construcción 2026-09-20

**Hecho (2026-09-19):** se eliminaron los comentarios que revelaban el historial de módulos
de negocio no relacionado (compras, POS, fidelización, soporte) en 13 archivos del backend y
frontend — quedaron solo las explicaciones funcionales necesarias, sin la referencia histórica.

Auditoría completa (flujo multi-agente: recon estático de docs vs código, revisión
adversarial de seguridad, pruebas en vivo contra un stack Docker de test, suite de tests
inicial, auditor final con trazado de escenarios). Stack de prueba: aislado, puertos
58100-58105, con datos de prueba propios — no toca nada de producción.

**Hecho (2026-09-20) — Ronda 1 del plan de construcción** (ver roadmap completo al final de
este archivo): implementación → revisión adversarial → feedback → auditor final → pruebas
(incluida verificación visual real en navegador), con gating estricto entre fases. Todos los
bloqueadores 🔴 de la auditoría del 19 quedaron resueltos y verificados en vivo, no solo en
código:

1. ✅ **Bypass de rate-limit/CAPTCHA por spoofing de IP** — `_get_real_ip()` ahora solo confía
   en `CF-Connecting-IP`/`X-Real-IP` si la IP real de la conexión (`request.client.host`) está
   en `TRUSTED_PROXY_IPS` (nueva config, vacía por defecto). Verificado en vivo dos veces
   (incluida una repetición completa post-reinicio de PC): rotar el header ya no bypasea el
   límite, 429 real desde el intento 8. Test de regresión: `tests/test_auth_ip_spoofing_fixed.py`.
   **Deuda residual, no bloqueante:** `TRUSTED_PROXY_IPS` queda vacío en `docker-compose.prod.yml`
   real — falta decidir el mecanismo para que el rate-limiting funcione bien detrás del
   contenedor `frontend` en producción (su IP en la red `internal` no es estática sin config
   adicional). Además, `_enforce_public_share_rate_limit` (`files/router.py`) sigue usando
   `request.client.host` directo sin pasar por este mecanismo — no es explotable (nunca confía
   en headers), pero en prod detrás de nginx todo el tráfico público de shares comparte un
   único balde de 30 req/min, indistinto por visitante real.
2. ✅ **DoS de 2FA por colisión de prefijo JWT** — la clave de rate-limit ahora usa el `jti`
   real de la sesión, no un prefijo fijo. Verificado en vivo con dos usuarios en paralelo: uno
   se bloquea, el otro no. Test: `tests/test_2fa_dos_fixed.py`.
3. ✅ **Código de reset en logs sin importar entorno** — el logger de archivo ahora queda en
   `INFO` fuera de `development`/`local` (antes `DEBUG` incondicional).
4. ✅ **Backend root/read-only** — `Dockerfile` corre como `appuser` (uid 1000, no-root);
   `docker-compose.yml` tiene `read_only: true` + `tmpfs` en `/tmp` y `/app/logs`. Confirmado
   con `docker inspect` (`ReadonlyRootfs=true`) y `docker exec ... id` contra la imagen real
   reconstruida, con la suite completa pasando encima.
5. ✅ **`/auth/register` ignora el flag** — ahora chequea `user_registration_enabled` y
   devuelve 403 si está apagado. Verificado en vivo (apagar → 403 → reactivar → 201 de nuevo).
6. ✅ **Provisioning de tenants roto** — `sembrar_cliente_nuevo()` ya no referencia el
   directorio inexistente `scripts/instalacion/cliente_nuevo/`; llama directo a la lógica de
   `scripts/seed_permissions.py`/`scripts/create_super_admin.py` (ambos refactorizados para
   exponer funciones reusables, sus `main()` de CLI siguen intactos).
7. ✅ **`minio/minio:latest` sin pin** — migrado a `quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z`
   en `docker-compose.yml` y `docker-compose.prod.yml`. Confirmado que el pull real funciona
   desde cero (Docker Hub efectivamente despublicó `minio/minio` el 2026-09-11).
   **Deuda residual:** `docker-compose.prod.yml` está en `.gitignore` — estos cambios (y
   cualquier otro que se haga ahí) nunca llegan a git, viven solo en el filesystem de cada
   servidor. Si el compose de producción real difiere del de este repo de trabajo, hay que
   aplicar el mismo pin a mano ahí.

**Bug encontrado y corregido durante la Ronda 1** (no estaba en la lista original, lo
descubrió el propio Auditor Final): el toggle de favoritos (`PATCH /files/{id}` y
`PATCH /folders/{id}` con `is_favorite`) había quedado atrás del mismo permiso que
renombrar/mover (`files.rename`/`files.move`), que el rol USER por defecto no tiene —
favoritos no funcionaba para el caso de uso principal. Corregido: favoritear ahora solo
exige el permiso de visualización + ownership (ya validado). El primer test que se escribió
para esto esquivaba el bug con un `grant_permission` manual en vez de exponerlo — se corrigió
también, y se agregó un test de regresión que confirma que renombrar/mover siguen exigiendo
su permiso real.

**Bug menor encontrado incidentalmente durante la verificación visual** (fuera del alcance
de la Ronda 1, sin investigar ni arreglar todavía): alternar a "modo claro" con el botón de
tema no aplica visualmente el cambio (el `<html>` pierde la clase `dark` pero la página sigue
viéndose en dark) — posible bug de theming preexistente, no relacionado a esta ronda.

**Hecho (2026-09-20) — Ronda 2 del plan de construcción: etiquetas.** Módulo nuevo
`app/tags/` (etiqueta personal por usuario, tablas puente `file_tags`/`folder_tags`
many-to-many), CRUD de etiquetas + reemplazo completo del set de un archivo/carpeta vía
`PUT /files|folders/{id}/tags` (todo-o-nada en ownership: si un solo `tag_id` no pertenece al
usuario, rechaza el request completo sin aplicar el resto), filtro `?tag_id=` en el listado,
chips visibles en fila y grilla con color, modal de asignación con confirmación de borrado.
Pasó por implementación → revisión adversarial (2 agentes) → feedback (3 fixes de UX en el
frontend: confirmación de borrado con `DeleteConfirmDialog`, accesibilidad del botón de
borrar, refresco del listado tras cancelar) → auditor final, con verificación en vivo
(incluida medición real de DOM para confirmar el truncado de nombres largos) y un escenario
de punta a punta con un usuario de rol USER real sin permisos extra. Sin bloqueadores.

**Deuda de diseño aceptada, no bloqueante:** `PUT /files|folders/{id}/tags` exige el permiso
de visualización (`files.view`/`folders.view`), no el de gestión de etiquetas (`tags.manage`)
— mismo criterio que se fijó para favoritos en Ronda 1 (favoritear/etiquetar un recurso propio
no debería requerir un permiso de escritura elevado). Ownership sigue validado siempre
(`_resolve_owned_tags`), así que no es una brecha real hoy — los roles ADMIN/USER tienen ambos
permisos simultáneamente. Solo importaría si en el futuro se crea un rol con `files.view` pero
sin `tags.manage` a propósito.

**Hecho (2026-09-20) — Ronda 3 del plan de construcción: compartir granular.** `Share`
extendido con contraseña opcional en links públicos (`password_hash`, header
`X-Share-Password`, nunca query param — evita que quede en logs/Referer), permiso
lectura/escritura (`permission`, solo aplica a shares dirigidos, un link público siempre es de
solo lectura), y compartir a un usuario específico por email (`shared_with_user_id`) con
notificación real al destinatario (`GET /shares/with-me`, página nueva "Compartido conmigo").
Con `permission=edit`: el destinatario puede subir archivos a una carpeta compartida o
reemplazar el contenido de un archivo compartido, con las MISMAS validaciones que un upload
normal (magic bytes, cuota) — la cuota se descuenta del dueño real, nunca del destinatario, y
el archivo subido queda con `owner_id` del dueño (el destinatario no puede gestionarlo como
propio ni re-compartirlo). Pasó por implementación → revisión adversarial (2 agentes) →
feedback (backend: enriquecer `with-me` con nombre del recurso y quién compartió; frontend:
agregar el formulario de contraseña que faltaba en la página pública) → una segunda vuelta de
feedback por un **bug crítico** que encontró la revisión adversarial (mismatch `id` vs
`share_id` entre backend y frontend, dejaba "Compartido conmigo" 100% inutilizable — ya
corregido y reverificado con las 5 acciones funcionando de punta a punta, incluida
confirmación visual del Auditor Final en navegador real) → auditor final. Suite: 43 tests.

**Deuda residual nueva, no bloqueante:** los endpoints autenticados de shares dirigidos
(`GET /shares/{id}`, su download, `POST .../files`, `PUT .../content`) no tienen rate-limit
propio (sí lo tienen los públicos). Confirmado en vivo que no es explotable como IDOR (sigue
exigiendo `current_user.id` en `(shared_with_user_id, created_by_id)`, y UUIDv7 da ~122 bits
de aleatoriedad), pero falta defensa en profundidad contra abuso/hostigamiento desde una cuenta
ya autenticada.

**Hecho (2026-09-20) — Ronda 4 del plan de construcción: versionado de archivos.** Tabla
`file_versions` nueva: todo archivo tiene una v1 automática al subirse (y las Rondas 1-3 que ya
existían recibieron backfill real de su v1 con la migración, 1029 filas), cada versión nueva
(`POST /files/{id}/versions`, o un reemplazo vía share con `permission=edit` de Ronda 3,
refactorizado para reusar la misma lógica) reserva cuota completa sin liberar la anterior (los
blobs viejos se conservan como historial real), y restaurar una versión vieja
(`POST .../versions/{id}/restore`) no sube nada nuevo — solo reapunta al blob existente, sin
costo de cuota adicional. La purga de papelera borra los blobs de TODAS las versiones, no solo
la actual. Pasó por implementación → revisión adversarial (2 agentes) → dos rondas de feedback
por **dos bugs ALTOS reales**:

1. La purga sobre-liberaba cuota de OTROS archivos del mismo dueño cuando el archivo purgado
   tenía un `restore` en su historial (`get_total_size_for_file` sumaba el mismo blob dos veces
   por no deduplicar por `storage_key` — mismo blob, dos filas de versión). Corregido, con un
   test de regresión que se confirmó atrapaba el bug original revirtiendo el fix a propósito.
2. La migración no hacía backfill de v1 para archivos preexistentes — subir una versión nueva
   sobre uno de esos archivos perdía el contenido original en silencio, sin aviso. Corregido
   con backfill idempotente dentro de la propia migración (con un segundo bug de idempotencia
   detectado y corregido en el camino).

Suite: 51 tests. El Auditor Final encontró además un **hallazgo de infraestructura, no de
código**: el contenedor `celery_worker` (el que ejecuta la purga real en producción, con
`--beat` embebido según `docker-compose.prod.yml`) había quedado con la imagen VIEJA, sin
`FileVersion` ni el fix — un rebuild de `backend` no alcanza si otro servicio comparte el mismo
código. Ya reconstruido y confirmado (`FileVersion` presente, código de purga corregido
verificado por inspección del módulo real cargado en ese contenedor).

**Nota de proceso para rondas futuras y para cualquier deploy real:** cualquier cambio a
código compartido (ej. `app/files`, `app/worker`) exige reconstruir TODOS los servicios que lo
importan (`backend` Y `celery_worker`, al menos), no solo el que se probó manualmente — quedó
demostrado que es fácil dar una ronda por "desplegada" cuando en realidad un servicio secundario
sigue corriendo código viejo sin que nada lo avise.

**Hecho (2026-09-20) — Ronda 5 del plan de construcción: preview extendido.** Video
(mp4/webm/ogg) y audio (mp3/wav/ogg) se sirven inline con reproductor nativo del navegador,
verificados por magic bytes con el mismo criterio de seguridad que ya se usaba para imágenes
(contenido que no confirma el tipo declarado se degrada a `application/octet-stream` y fuerza
descarga). Documentos de Office (docx/xlsx/pptx + legacy) se convierten a PDF mediante un
**servicio Docker nuevo y aislado** (`filemeshy_office_converter/`, LibreOffice headless) y se
cachean por `file_id`+`version_number` en MinIO (se invalidan solos al subir una versión nueva
o restaurar una vieja, aprovechando el versionado de la Ronda 4). Antes de construir, se
investigó cómo lo resuelven Nextcloud/Seafile/ownCloud (los tres usan LibreOffice headless; el
enfoque maduro de la industria es aislarlo en un contenedor separado y no privilegiado, no
embebido en el proceso principal — ownCloud incluso marca el modo embebido como "unsupported").

El servicio nuevo quedó endurecido según las CVEs reales de RCE en LibreOffice
(CVE-2024-12425/12426, 2025-0514, 2025-1080, todas parcheadas en la versión instalada): corre
como no-root, filesystem read-only, `cap_drop: [ALL]`, `no-new-privileges`, límites de recursos
(1 CPU/1GB/128 pids), perfil de LibreOffice con macros deshabilitadas y sin auto-fetch de
enlaces externos, timeout de 30s con kill del process group completo, **sin puerto expuesto al
host** — solo alcanzable desde `backend` por la red interna de Docker. Un intento real de
SSRF/exfiltración vía documento malicioso (campos `INCLUDETEXT`/`INCLUDEPICTURE` de Word y
`WEBSERVICE()` de Excel apuntando a servicios internos del stack) se probó en vivo contra el
servicio real y **no se resolvió ningún link externo** — el hardening del perfil de LibreOffice
funciona en la práctica, no solo en la teoría.

Pasó por implementación (3 agentes: backend, servicio conversor, frontend) → revisión
adversarial (2 agentes) → dos rondas de feedback por:

1. **[MEDIO]** El backend no validaba el tamaño del archivo antes de reenviarlo al conversor —
   un Office de 50-100MB viajaba completo por la red interna en cada pedido, siempre fallaba, y
   como nunca se cacheaba el costo se repetía. Tampoco había rate-limit en el endpoint de
   preview. Corregido: chequeo fail-fast contra `size_bytes` (confirmado en vivo: rechazo en
   0.0076s, no el tiempo que tomaría transferir 50MB+) + rate-limit de 15 conversiones/min por
   usuario.
2. **[CRÍTICO]** Mismatch de contrato entre backend (`preview_url`) y frontend (leía `.url`,
   inexistente) dejaba el preview de Office en un modal completamente en blanco, sin spinner ni
   error — el usuario no tenía forma de saber qué pasó. Corregido y reverificado con evidencia
   rigurosa (contenido real del PDF extraído con `pdftotext` y comparado byte a byte con el
   documento original, no solo capturas de pantalla).

Suite: 71 tests.

**Deuda residual nueva, no bloqueante (defensa en profundidad):**

- El servicio `office_converter` comparte la red Docker `filemeshy_default` con TODO el stack
  (postgres, redis, minio, frontend, celery_worker) y no tiene autenticación de aplicación
  propia — hoy nada más que `backend` lo llama, pero cualquier contenedor de esa red PODRÍA
  hacerlo si se comprometiera por otra vía no relacionada, sin pasar por ownership/cuota/límites
  del backend. Recomendado: red interna dedicada `backend`↔`office_converter`, y/o un secreto
  compartido validado por el propio servicio.
- El `<iframe>` de `PreviewModal.tsx` que embebe PDFs (nativos y convertidos) no tiene atributo
  `sandbox` — hoy no es explotable porque el Content-Type se verifica server-side por magic
  bytes antes de servir, pero es una capa de defensa en profundidad ausente si esa cadena
  llegara a regresionar.
- Rebuild periódico de la imagen de `office_converter` (con `--no-cache`/`--pull`) necesario
  para seguir recibiendo parches de seguridad de Debian sobre LibreOffice — no alcanza con "no
  tocar el Dockerfile", si no se reconstruye la versión se cristaliza.

**Hecho (2026-09-21) — Ronda 6 del plan de construcción: búsqueda por contenido + OCR.**
Tabla `file_content_index` (1:1 con `File`, `search_vector` tsvector generado por Postgres +
índice GIN). Extracción de texto **asíncrona** vía Celery (cola `indexing` dedicada, para no
competir con notificaciones/emails): texto plano directo, PDF con `pypdf` + fallback a OCR si
el texto embebido es casi vacío (PDF escaneado, tope 20 páginas), Office moderno
(docx/xlsx/pptx) con librerías directas sin pasar por LibreOffice, imágenes con OCR directo
(Tesseract, agregado a la misma imagen que ya comparten `backend`/`celery_worker` — mismo
perfil de riesgo que pyvips, ya aceptado). Se dispara al subir un archivo, subir/restaurar una
versión, o reemplazar contenido vía share con `permission=edit`. `CRUDFile.search` ahora
matchea nombre O contenido, con `matched_by: 'name'|'content'|'both'` en la respuesta y un
badge visible en el frontend (Lista y Grilla) solo cuando hay búsqueda activa.

Pasó por implementación (2 agentes) → revisión adversarial (2 agentes, cada uno encontró de
forma **independiente** el mismo bug crítico desde ángulos distintos):

1. **[CRÍTICO]** El workaround de "importar todos los modelos antes de usar el ORM en una
   tarea Celery" (ya necesario desde antes para `maintenance.py`) solo se agregó a
   `indexing.py`, no a `email.py`/`security.py`. Si cualquiera de esas otras tareas corría
   PRIMERO en el proceso del worker, envenenaba el registro de mappers de SQLAlchemy **para
   todo el proceso**, y la indexación quedaba muerta hasta reiniciar el worker — reproducido
   en vivo dos veces por agentes distintos. Corregido centralizando el import en una señal
   `worker_process_init` de Celery (`celery_app.py`), que corre una sola vez por proceso antes
   de cualquier tarea — ya no importa el orden ni depende de que cada tarea nueva copie el
   workaround. Reverificado de forma independiente por 3 agentes distintos tras el fix
   (incluido un escenario real de OCR sobre una imagen con texto, de punta a punta).

Suite: 80 tests.

**Hecho (2026-09-21) — Ronda 7 (parte backups del plan de construcción).** Backup automático
de Postgres CON verificación real: tabla `backup_runs` nueva (`app/backups/`) registra CADA
corrida (`'running'`/`'success'`/`'failed'`, tamaño, dónde quedó guardada) — un backup que
nadie verifica no es un backup real, así que el diseño no es "correr un cron y esperar que
funcione". `backup_postgres` (Celery, diaria 2:00 AM, cola `maintenance`) corre `pg_dump` real
contra la Postgres del stack, comprimido con gzip, subido a un bucket privado nuevo de MinIO
(`filemeshy-backups`, sin política de lectura pública). Retención configurable
(`BACKUP_RETENTION_DAYS`, default 14 días): después de cada backup exitoso se borra el OBJETO
de los backups viejos en MinIO, pero la FILA `BackupRun` se conserva como registro histórico
auditable. Endpoints admin nuevos (`GET/POST /admin/backups`, permiso `backups.view`) para
listar corridas y disparar un backup manual sin esperar al horario. Test real (no mockeado):
corre `pg_dump` de verdad, confirma que el objeto EXISTE en MinIO con el tamaño correcto, y que
la retención borra un backup viejo simulado de verdad (objeto + limpieza de `storage_location`).

**Limitación conocida, documentada a propósito (no un olvido):** el backup de MinIO
(`backup_minio_objects`) es **CONDICIONAL** — un backup de TODO el contenido de MinIO
(`filemeshy-media` + `filemeshy-media-private`) sería caro (duplica el storage completo) y, si
el destino fuera el MISMO disco/servidor donde ya vive MinIO, **no protegería contra una falla
de disco real** (daría una falsa sensación de seguridad, peor que no tener backup y saberlo).
Por diseño, esta tarea SOLO copia objetos si están configuradas las 4 variables de un destino
S3-compatible **EXTERNO** (`BACKUP_S3_ENDPOINT`/`BACKUP_S3_BUCKET`/`BACKUP_S3_ACCESS_KEY`/
`BACKUP_S3_SECRET_KEY`) — ninguna tiene default, y **este stack (dev/test y producción tal cual
está hoy) no las tiene configuradas**. Sin esa config: `backup_minio_objects` se registra en
`backup_runs` como `status='failed'` con el motivo explícito ("falta destino S3 externo"),
visible en `GET /admin/backups` — nunca finge que hay backup de archivos cuando no lo hay.
**Acción pendiente real, no solo teórica:** para tener backup de archivos de verdad, hay que
contratar/aprovisionar un S3-compatible externo (otro proveedor, otra región, otro servidor
físico) y setear esas 4 variables — hasta entonces, **los archivos de usuario en MinIO NO
tienen backup**, solo la base de datos (metadatos, no el contenido de los archivos en sí).

Módulo backend nuevo: `app/backups/` (`models.py`, `schemas.py`, `repository.py`, `router.py`),
`app/worker/tasks/backups.py`, migración `d4e8a1f2b9c6`. Página nueva de frontend "Copias de
Seguridad" (tabla con estado/tamaño/duración de cada corrida, botón "Ejecutar backup ahora",
badge gris/informativo — no rojo de alarma — cuando MinIO da `failed` por falta de config,
distinto de un fallo real).

**Hallazgo CRÍTICO real, encontrado por la revisión adversarial y ya corregido (2026-09-21):**
`backups.view` se agregó a `CANONICAL_PERMISSIONS`/`ROLE_PERMISSIONS_CANONICAL['ADMIN']` en
`app/core/permissions.py`, pero nadie corrió `scripts/seed_permissions.py` contra la BD real —
`has_permission()` en runtime lee `User.permissions`, una columna CACHEADA que se calcula desde
las tablas reales `permissions`/`role_permissions`, nunca desde el dict de código directo. Sin
el seed, esas tablas seguían sin la fila nueva y un ADMIN real (no `SUPER_ADMIN`, que bypasea el
chequeo por completo) recibía 403 real en `GET/POST /admin/backups` — confirmado en vivo con
`SELECT ... FROM permissions WHERE permission_code='backups.view'` devolviendo 0 filas.

Los 6 tests originales de esta ronda no lo agarraron porque usaban `grant_permission()`
(`tests/conftest.py`) — bypass directo de la columna JSON del usuario, sin tocar `role_id` ni
`role_permissions` — nunca ejercitaban el camino real de un ADMIN. Corregido con un helper nuevo,
`make_real_admin()` (mismo archivo): asigna `role_id`=ADMIN de verdad, corre
`scripts/seed_permissions.py` (idempotente) y recalcula `User.permissions` desde la tabla real —
el mismo mecanismo que dispara `PUT /users/{id}` con un `role_id` nuevo. Test de regresión nuevo,
`test_real_admin_role_can_list_and_trigger` (`tests/test_backups_endpoints.py`), y advertencia
agregada al inicio de `app/core/permissions.py` para que el próximo permiso nuevo no repita el
mismo bug. Reproducido y reverificado en vivo dos veces: se borró a mano la fila real de
`permissions`/`role_permissions` en la BD del stack, se confirmó que el test nuevo la detecta (y
la repuebla vía el seed idempotente que corre como parte del propio helper), y se re-confirmó
limpio. En el camino se encontró y corrigió un segundo bug menor: `make_real_admin()` era el
primer código de test que hacía una query ORM directa sobre `User` sin pasar por HTTP, y en un
proceso de pytest completamente fresco (aislado) disparaba el mismo bug de mapper de SQLAlchemy
de la Ronda 6 (`User.sessions = relationship("Session", ...)` sin resolver) — corregido
importando `app.worker.celery_app` antes de la query (dispara el fix centralizado de esa Ronda).
Además, la revisión adversarial encontró **2 bugs más en el frontend de Backups** (mismo
agente de implementación, corregidos en la misma vuelta de feedback): el backend devuelve
`{items, total}` en `GET /admin/backups`, pero el service del frontend esperaba un array plano
— la tabla mostraba "No se encontraron backups" **siempre**, aunque hubiera corridas reales
(confirmado en vivo: 18+ filas reales en la BD, tabla vacía en pantalla). Y el gate de permiso
de la ruta/botón usaba `settings.edit_system` en vez de `backups.view` — rompía la granularidad
que el propio backend define (un permiso, `backups.view`, para todo lo de backups). Ambos
corregidos y reverificados visualmente en navegador real tras el rebuild, incluido un usuario
sin el permiso confirmando que no ve el ítem de nav y es bloqueado por URL directa.

Suite completa reverificada tras todos los fixes: **94 passed, 0 failed**.

**Hecho (2026-09-21) — Ronda 7 (parte antivirus).** Escaneo de malware en TODO contenido nuevo
que entra al sistema, antes de subirlo a MinIO: subida directa, subida a carpeta compartida
(`permission=edit`), nueva versión de archivo, y reemplazo de contenido vía share. Servicio
Docker nuevo y aislado con la imagen OFICIAL `clamav/clamav:stable` (sin build custom, a
diferencia del conversor de Office de Ronda 5 — ClamAV ya trae `freshclam` integrado), sin
puerto expuesto al host, volumen nombrado persistente para la base de firmas,
`cap_drop:[ALL]` + `cap_add` mínimo justificado (`CHOWN,FOWNER,DAC_OVERRIDE,SETUID,SETGID`,
necesarios para que el entrypoint oficial baje privilegios de root a `clamav`) — confirmado en
vivo que `clamd`/`freshclam` corren como no-root, solo el proceso supervisor (`tini`) queda
root. Escaneo vía protocolo TCP INSTREAM implementado a mano (sockets crudos, sin librería de
terceros, para máximo control del manejo de errores en un componente de seguridad crítico).
Política **fail-closed real**: contenido infectado → 422 sin subir nada; `clamd` inalcanzable o
con timeout → 503, nunca se acepta sin escanear.

La revisión adversarial encontró **2 hallazgos MEDIUM de disponibilidad, ambos reproducidos en
vivo (no teóricos) y corregidos**:

1. El escaneo bloqueaba el event loop async COMPLETO, no solo la request de quien subía —
   durante un escaneo real de ~2s, otro usuario haciendo `GET /files` en simultáneo vio su
   latencia subir de 0.02s a 1.83s. Corregido moviendo el escaneo a threadpool
   (`starlette.concurrency.run_in_threadpool`).
2. El timeout configurado (`CLAMAV_SCAN_TIMEOUT_SECONDS`) no era un deadline TOTAL — se
   reseteaba en cada operación de socket individual. Con un `clamd` degradado devolviendo la
   respuesta a los tumbos, el escaneo tardó 15s con un timeout de 2s configurado (7.5x).
   Corregido con un deadline real basado en `time.monotonic()`, calculado una vez y verificado
   antes de cada operación de red.

Ambos fixes reverificados en vivo por el Auditor Final de forma independiente: 10 escaneos
EICAR en paralelo + 1 upload limpio simultáneo no afectaron la latencia del upload limpio
(0.148s, igual al baseline sin concurrencia). EICAR real probado con éxito en los 4 puntos de
entrada — 422 en todos, cero rastro en BD/MinIO. Un usuario real de rol USER subiendo archivos
normales no percibe fricción (23-42ms por subida).

Suite: 7 tests nuevos de antivirus, incluidos 2 de regresión para los hallazgos de arriba.

**Deuda residual nueva, no bloqueante:**

- `_extract_pdf_text` (texto embebido real, no el fallback OCR) no tiene tope de páginas —
  a diferencia de `_ocr_pdf` que sí limita a 20. Un PDF de texto con miles de páginas simples
  cabría en el límite de subida (100MB) y consumiría CPU del worker hasta el `time_limit`
  global de la tarea (180s). No explotable de forma crítica (el hard kill corta la tarea), pero
  conviene un tope simétrico al de OCR.
- Combinación `task_acks_late=True` + `task_reject_on_worker_lost=True` + `time_limit` duro en
  `index_file_content`: si el `SIGKILL` del límite duro llega antes de que la tarea alcance a
  marcar `extraction_status='failed'`, el mensaje puede no ackearse y Celery lo redelivera sin
  tope de reintentos a nivel de broker — un archivo que confiablemente exceda el límite podría
  generar redelivery indefinida sobre la cola `indexing`.

**Hecho (2026-09-22) — Ronda 8 del plan de construcción: UI de administración de tenants — cierra el roadmap completo.**
Panel de administración de tenants SEPARADO del panel admin normal de la app, en rutas
propias `/plataforma/login` y `/plataforma/tenants` — decisión de arquitectura confirmada con
el usuario antes de construir: el provisioning de tenants ya estaba protegido por un header
`X-Platform-Key` (secreto de plataforma, no JWT/RBAC normal), a propósito, para que ningún
admin de una empresa cliente pueda ver/crear otros tenants (aislamiento cross-tenant ya
documentado en el propio código desde antes de esta ronda). Integrarlo al RBAC normal habría
requerido inventar un concepto de "super-admin de plataforma" inexistente en el modelo de
usuarios (cada usuario vive en un solo tenant/schema) y habría debilitado ese aislamiento a
propósito — se descartó esa opción.

Backend: nuevo `PATCH /platform/tenants/{tenant_id}` (activar/desactivar, cambiar plan) + rate
limiting real sobre `get_platform_admin` (10 intentos fallidos/15min por IP, reusa
`RateLimiter` y `_get_real_ip` ya existentes de la Ronda 1, el 429 dispara ANTES de comparar la
key). Frontend: módulo nuevo `src/modules/platform_admin/` con su propio cliente HTTP
standalone (key en `sessionStorage`, no `localStorage`; sin JWT/CSRF/cookies), fuera de
`Sidebar`/RBAC — solo alcanzable tipeando la URL directamente.

Pasó por implementación (2 agentes, backend/frontend en paralelo) → revisión adversarial (2
agentes: seguridad + producto/correctitud) → feedback → auditor final → pruebas (2 agentes de
confirmación independiente), con gating estricto entre fases. Hallazgos, todos corregidos y
reverificados en vivo:

1. **[MEDIO]** `TenantCreateResponse` no declaraba el campo `admin_email` — Pydantic lo
   descartaba en silencio al armar la respuesta de creación, aunque el servicio ya lo calculaba
   internamente; el panel de credenciales del tenant recién creado quedaba con el email vacío.
   Corregido, con test de regresión.
2. **[MEDIO]** `tenant_id` sin tipar como `UUID` en el GET-por-id y en el PATCH nuevo — un
   valor malformado en la URL explotaba con `DataError` de Postgres → 500 genérico, en vez de
   un 422 limpio antes de tocar la base. Corregido tipando `UUID` (mismo patrón ya usado en el
   resto del codebase), con test de regresión.
3. **[CRÍTICO, de proceso]** `docker-compose.override.yml` (creado puntualmente para poder
   probar el modo `cloud` en el stack de dev/test) forzaba `DEPLOYMENT_MODE=cloud` +
   `PLATFORM_API_KEY` de prueba, y quedó sin trackear en git y **sin gitignorear**. Mientras
   estuvo puesto rompió las 94 tests preexistentes (en modo cloud, `TenantMiddleware` exige
   `X-Tenant-Slug` en toda request y ningún test viejo lo manda) y, más grave, habría roto la
   APP NORMAL completa (login, archivos, todo) para cualquiera que clonara el repo y corriera
   `docker compose up` sin saberlo — Compose lo mergea automáticamente, sin necesitar `-f`.
   Resuelto: agregado a `.gitignore` con el motivo documentado; el archivo se sacó del checkout
   activo al cerrar la ronda y el stack quedó de nuevo en modo `local` por defecto, confirmado
   con la suite completa en verde.
4. **Frontend — 6 hallazgos de UX/correctitud** de la revisión adversarial, corregidos y
   reverificados con Playwright: estado de error indistinguible de "lista vacía"; un guard
   (`isToggling`) que aparentaba proteger contra el cierre prematuro del diálogo de confirmación
   y en realidad no lo hacía (reemplazado por un estado real por fila); las 2 rutas nuevas sin
   `errorElement` (único caso en toda la app); flicker breve mostrando "no hay datos" durante la
   carga inicial; mensaje de login engañoso ante un fallo de red real (mostraba "clave
   incorrecta" en vez de "no se pudo conectar al servidor"); y un comentario de código
   desactualizado.

Suite: 94 + 8 = 102 tests. Los 8 nuevos de `test_platform_tenants.py` quedan **SKIPPED** en modo
`local` por defecto (`pytestmark` condicionado a `DEPLOYMENT_MODE=cloud`) y pasan 8/8 cuando se
activa el modo cloud puntualmente para probarlos. Suite completa reverificada de forma
independiente por 2 agentes tras cerrar la ronda: **94 passed, 8 skipped, 0 failed** en modo
local (el modo real de este stack y de producción hoy).

**Deuda residual nueva, no bloqueante:**

- No hay ningún mecanismo de sesión del lado servidor para el panel de plataforma — la key se
  pega directo en un form y viaja como header en cada request; es consistente con el nivel de
  confianza que `X-Platform-Key` ya exigía desde antes de esta ronda, pero no hay expiración más
  allá de cerrar la pestaña (`sessionStorage`) ni ningún registro de auditoría de quién usó la
  key y cuándo.
- La contraseña inicial del super admin generado al crear un tenant sigue sin viajar por la API
  (decisión de diseño preexistente, respetada a propósito en esta ronda) — el operador tiene que
  copiarla de los logs del contenedor `backend` y entregarla por un canal seguro; el panel nuevo
  lo explica en pantalla pero no lo resuelve.
- Para volver a probar el panel de plataforma en el futuro hace falta recrear un
  `docker-compose.override.yml` puntual (2 líneas: `DEPLOYMENT_MODE=cloud` +
  `PLATFORM_API_KEY`) — ya documentado en el comentario del `.gitignore`, pero no hay ninguna
  guía paso a paso en el repo.

**Hecho (2026-09-22) — Ronda 9, post-roadmap: subida de archivos grandes (10-20GB) sin
saturar el servidor, resumable, sin crecer horizontal ni verticalmente.** Pedido explícito del
usuario tras el cierre del roadmap original de 8 rondas: 10 personas subiendo en simultáneo 1-2
archivos de 10-15GB cada una rompía el sistema (el backend leía cada archivo COMPLETO a RAM
antes de escanear/subir, sin límite de memoria en el contenedor). Investigación previa (interna y
externa, Nextcloud/ownCloud/tus.io/S3 multipart) llevó a la arquitectura implementada, la misma
que usan los proyectos open-source maduros investigados:

- **Subida multipart directa navegador→MinIO** vía URLs presignadas (S3 multipart), pasando por
  un proxy de nginx que reenvía en streaming (`proxy_request_buffering off`) — los bytes NUNCA
  tocan la memoria del proceso backend. Resumabilidad real y gratuita: cada parte (256MB) es
  reintentable por separado; si se corta la conexión o se cierra la pestaña/reinicia la PC, al
  volver el cliente pide `ListParts` real contra MinIO y solo sube lo que falta — verificado en
  vivo con archivos de hasta 700MB (varias partes) cortando la conexión a mitad y recargando la
  página a mitad de una subida real, sin resubir nada ya confirmado.
- **Antivirus asíncrono con gate de visibilidad** (mismo patrón que Nextcloud/ownCloud,
  confirmado por investigación): el archivo queda `scan_status='pending'` — invisible para TODOS,
  ni el propio dueño lo ve/descarga/comparte — hasta que un worker de Celery lo escanea en
  streaming real desde MinIO (nunca bufferiza el archivo completo, confirmado con `docker stats`
  en vivo: memoria del worker estable independiente del tamaño del archivo). Limpio → visible +
  indexado para búsqueda por contenido (si ≤512MB, tope propio para no reintroducir el problema
  de memoria del lado del worker de indexación de la Ronda 6). Infectado → cuarentena real (objeto
  movido a bucket separado, original borrado, fila `File` conservada como registro auditable, NO
  borrada) + notificación. `clamd` inalcanzable → fail-closed real, reintentos con backoff, nunca
  pasa a `clean` sin confirmación. **Los uploads chicos (≤100MB) siguen exactamente igual que
  antes** — síncronos, sin cambios; esta ronda solo agrega un segundo camino para archivos
  grandes, no debilitó la seguridad existente.
- **Cuota reservada por adelantado** (atómica, ya existente desde Ronda 1), con verificación real
  del tamaño final contra lo reservado al completar (un cliente no puede declarar de menos y
  subir de más). **Admission control** con tope global Y por usuario (`MAX_CONCURRENT_LARGE_UPLOADS`/
  `_PER_USER`) para no saturar el I/O de disco de MinIO ni la cola de escaneo con demasiadas
  subidas grandes simultáneas, con limpieza autorecuperable en horas (no días) de sesiones
  abandonadas.

Pasó por el flujo completo: recon (interno + investigación externa) → implementación (3 agentes
en paralelo: coordinación/cuota, antivirus/infra, frontend) → revisión adversarial (2 agentes:
seguridad, producto/correctitud) → feedback → auditor final → pruebas (2 agentes de confirmación
independiente) → una segunda vuelta de feedback por un hallazgo real que apareció recién en
Pruebas. Bugs reales encontrados y corregidos en el camino:

1. **[3 bugs de integración, encontrados y corregidos durante la implementación misma, antes de
   la revisión adversarial]** El proxy nuevo de nginx rompía la firma SigV4 de las URLs
   presignadas de tres formas distintas, cada una encontrada recién al probar en vivo contra el
   proxy real (nunca visibles probando la firma o nginx por separado): (a) el `Host` que nginx
   reenviaba a MinIO estaba hardcodeado en vez de preservar el original; (b) un prefijo de path
   artificial (`/storage-proxy`) quedaba parte del recurso firmado por SigV4, pero MinIO usa ESE
   MISMO path para resolver el bucket — estructuralmente no había forma de que un path
   satisficiera ambas cosas a la vez, se resolvió reusando el location de descarga YA EXISTENTE
   (sin prefijo artificial) en vez de uno nuevo; (c) `$host` de nginx descarta el puerto del Host
   entrante, y con `SignedHeaders=host` el puerto también es parte de lo firmado — corregido a
   `$http_host`. Confirmado en vivo de punta a punta (PUT real de datos → 200 con ETag real de
   MinIO) recién después de los 3 fixes juntos.
2. **[ALTO, revisión adversarial de seguridad]** DoS trivial de admisión: un solo usuario podía
   agotar TODO el cupo global de subidas grandes abriendo sesiones sin completarlas ni abortarlas
   (sin límite por usuario), bloqueando la feature para todos los demás hasta 48-54hs (el TTL de
   reanudación de sesión se compartía con el TTL del cupo de concurrencia). Corregido: tope por
   usuario + TTL de admisión corto (4hs) y renovable, desacoplado del plazo de reanudación (48hs),
   con poda automática de miembros vencidos en cada chequeo (autorecuperable en horas, no en días,
   sin depender de la tarea periódica de limpieza).
3. **[MEDIO, revisión adversarial de seguridad]** Fuga permanente de cuota en archivos puestos en
   cuarentena — los bytes de un archivo infectado quedaban contados para siempre en la cuota del
   dueño, sin ningún camino de liberación (el archivo es invisible, no se puede ni ver para
   borrar). Corregido: se libera la cuota reservada al confirmarse la cuarentena.
4. **[Funcional, revisión adversarial de producto]** Los archivos subidos por el camino grande
   nunca quedaban indexados para búsqueda por contenido (la Ronda 6 nunca se conectó a este
   camino nuevo). Corregido, con tope de 512MB documentado (la tarea de indexación no fue
   diseñada para streaming, encolarla sin tope reintroduciría el problema de memoria original del
   lado del worker de indexación).
5. **[MEDIO/ALTO, encontrado en la fase de Pruebas, después del veredicto del Auditor Final]** El
   modal de subida quedaba completamente bloqueado (ni X, ni Escape, ni backdrop, ni navegar a
   otra página) mientras un archivo grande estaba en estado `uploading` — contradecía
   directamente el propósito de la ronda (subidas que pueden tardar horas, el usuario debería
   poder seguir usando la app). El motor de subida vive en un store global independiente del
   modal (ya existe un panel flotante, `UploadsTray`, para seguir viendo el progreso) — no había
   ninguna necesidad técnica real para el bloqueo, era un criterio heredado sin reconsiderar del
   camino simple (donde sí tiene sentido, ahí no se tocó). Corregido y reverificado en vivo con
   throttling de red real (16/16 aserciones): cerrar el modal a mitad de una subida real, navegar
   a otra página, la subida sigue y termina bien.

Suite: **112 passed, 8 skipped (feature condicional de Ronda 8, no relacionada), 0 failed** —
subió de 94 (fin de Ronda 8) a 112. Reverificada de forma independiente por 3 agentes distintos
en fases separadas (implementación, auditor final, pruebas), todas coincidiendo exacto.

**Deuda residual nueva, no bloqueante:**

- El header `Retry-After` que el backend manda en el 503 de admission control **nunca llega al
  cliente** — bug preexistente (no introducido por esta ronda): el manejador global de excepciones
  (`app/main.py::http_exception_handler`) reconstruye la respuesta descartando por completo
  `exc.headers`, afecta a CUALQUIER endpoint que use `HTTPException(headers=...)`, no solo este.
  Mitigado del lado frontend (ya no depende de ese header, usa un tope propio de reintentos), pero
  el bug de fondo sigue sin arreglar.
- `backup_minio_objects` (Ronda 7) podría en teoría llevarse copia de un archivo todavía
  `pending` (sin escanear) si el backup S3 externo se configurara algún día — hoy NO está
  configurado en ningún entorno real, riesgo puramente teórico.
- `scan_uploaded_file` (la tarea de escaneo asíncrono) no resuelve `tenant_schema` en
  `DEPLOYMENT_MODE=cloud` — no usado en ningún entorno real hoy, documentado en el docstring de
  la tarea para cuando/si se active.
- Gaps de cobertura de tests identificados por QA en la fase de Pruebas (no son bugs, son
  ausencia de test automatizado en caminos críticos): el camino fail-closed real de la tarea de
  escaneo (`clamd` inalcanzable → reintentos → `scan_failed`) se prueba llamando directo a un
  helper interno, no ejercitando el `try/except` real de la tarea completa — una regresión ahí
  pasaría en verde sin que ningún test la note. Tampoco hay ningún assert programático de que
  `scan_minio_object_for_malware` efectivamente hace streaming (la propiedad central de toda la
  ronda depende hoy de verificación manual con `docker stats`, no de un test automatizado). Y el
  tope GLOBAL de admisión (a diferencia del tope por usuario, que sí tiene test) nunca se prueba
  en aislamiento.
- La firma EICAR estándar de prueba deja de detectarse pasado los 68 bytes exactos (cualquier
  padding rompe la detección) — confirmado como comportamiento esperado de esa firma específica
  en toda la industria (evita falsos positivos masivos si alguien rellena un archivo real grande
  con el string EICAR), NO una falla real de ClamAV — se confirmó detección real con una firma
  de prueba sin esa restricción en archivos de hasta 600MB, en cualquier posición. Implicancia
  práctica: EICAR puro no sirve para probar/simular un archivo infectado por el camino grande en
  el futuro, hace falta una firma de prueba sin restricción de tamaño.

**Hecho (2026-09-22/24) — Ronda 10: cierre de deuda de la Ronda 9 y de la auditoría.** Ronda de
endurecimiento, sin features nuevas de producto. Cambios:

- **`Retry-After` ahora llega al cliente.** El 503 de admission control perdía sus headers
  porque `typed_exception_handler` (`app/api/v1/exception_handlers.py`) reconstruía la respuesta
  descartando `exc.headers`; el handler de `main.py` tenía el mismo defecto. Ambos fusionan ahora
  `exc.headers` con los headers CORS (CORS siempre gana). Hallazgo clave: el handler que gana
  para `fastapi.HTTPException` es el de `exception_handlers.py` (despacho por el tipo más
  específico del MRO), arreglar solo `main.py` no alcanzaba. Test: `test_upload_admission_retry_after.py`.
- **`python-jose` reemplazado por PyJWT 2.14.0** (`auth/service.py`, `core/security.py`);
  `cryptography` pasa a ser dependencia explícita (antes llegaba transitiva). Cierra
  CVE-2024-33663/33664.
- **Imágenes Docker fijadas por digest**: `postgres:15.19-alpine`, `redis:7.4.11-alpine`,
  `clamav/clamav:stable`, `python:3.11-slim`, `node:22-alpine`, `nginx:alpine`. Las tags ya no
  pueden re-apuntarse solas. **Costo operativo:** hay que actualizar los digests a mano para
  recibir parches de seguridad (ver el punto de rebuild periódico de la Ronda 5).
- **CSP del frontend endurecida** (`nginx.conf`): `default-src 'self'`, `script-src 'self'` +
  hash SHA-256 del único script inline (tema antes de pintar), `object-src 'none'`,
  `base-uri`/`form-action 'self'`, `connect-src 'self'`. `style-src 'unsafe-inline'` se mantiene
  a propósito (estilos inline dinámicos de React). **Si cambia el script inline de
  `index.html`, hay que recalcular el hash** (comando en el comentario de `nginx.conf`) o el
  tema se rompe en silencio.
- **`/assets/` recupera los 4 headers de seguridad** (bug de herencia de `add_header`).
- **`/health/detailed` reducido** a conectividad de BD + versión de la app: ya no expone versión
  de Postgres/Python/OS ni el flag `debug`.
- **`create_super_admin.py` valida el email** con `email_validator` (la misma librería del
  login) antes de insertar. Corrección al diagnóstico original: no era un chequeo de
  deliverability DNS (`EmailStr` lo tiene apagado), sino el rechazo incondicional de dominios
  especiales (`.local`, `.test`, `.invalid`, `.localhost`, `.onion`, `.arpa`). Test:
  `test_create_super_admin_email_validation.py`.
- **Menú ⋮ ya no se recorta** en la última fila: `Dropdown.tsx` renderiza el menú en un portal
  con `position: fixed`, reposicionado en scroll/resize.
- **Gaps de cobertura de la Ronda 9 cerrados**: fail-closed end-to-end de la tarea de escaneo,
  streaming con memoria acotada (assert programático) y tope global de admisión en aislamiento
  (`test_av_scan_async.py`, `test_large_upload_multipart.py`).

**Cierre y verificación en vivo (2026-09-25).** Se reconstruyeron `backend`, `celery_worker` y
`frontend` y se recreó el stack completo (estaba caído). Resultado:

- **Suite completa: 123 passed, 8 skipped, 0 failed** (los 8 skipped son `test_platform_tenants.py`,
  solo corren en modo `cloud`). Subió de 112 a 123 con los tests de la Ronda 10.
- **Headers reales con curl:** CSP nueva presente en `/` y en `/assets/*`; `/assets/` conserva
  `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy` y `X-Content-Type-Options`. El hash
  SHA-256 de la CSP coincide con el script inline del `index.html` servido.
- **Navegador real (Playwright/Chromium), sin ninguna violación de CSP en consola:** login,
  dashboard, página de Archivos, subida de 2 archivos, preview de imagen desde MinIO
  (`naturalWidth` 200, el origen `:58102` permitido por `img-src` funciona), y tema claro/oscuro
  persistido tras recargar (el script inline con hash se ejecuta).
- **`Retry-After` en vivo:** al abrir una 4ª sesión de subida grande, el 503 real llega con
  `Retry-After: 30` (bug original reproducido y confirmado resuelto). Al abortar las sesiones el
  cupo se libera (siguiente `initiate` → 201).
- **`/health/detailed`:** sin auth responde 401 (sigue gateado); `/health` público sin detalle.
- **PyJWT:** el login emite y valida tokens con la librería nueva.
- **Email `.local`:** `create_super_admin.py` lo rechaza con mensaje claro; con dominio válido crea
  la cuenta y el login funciona.

**Defecto encontrado y corregido durante el cierre:** el fix del menú ⋮ de la primera versión de
la Ronda 10 (portal con `position: fixed`) dejaba los últimos ítems INALCANZABLES con una
ventana baja (a 480px de alto el menú de 335px se salía del viewport y, al ser `fixed`, no se
podía scrollear a él). Ahora `Dropdown.tsx` abre hacia arriba cuando abajo no entra y hay más
lugar arriba, y acota `maxHeight` al espacio disponible con scroll interno. Verificado en
navegador real a 800/600/480/320px de alto: el menú queda dentro del viewport y el último ítem
("Eliminar") es alcanzable en todos.

**Bug del modo claro: NO reproducible.** En el build actual el toggle cambia la clase de `<html>`,
el fondo cambia (`rgb(3,7,17)` → `rgb(246,247,249)`) y persiste al recargar. Se cierra como no
reproducible; si vuelve a aparecer, reabrir con pasos exactos.

**Hallazgo nuevo, sin corregir:** el modal de subida muestra "Tamaño máximo: 1073741824MB" — son
bytes rotulados como MB (`FileUpload.tsx` / uso en el modal de subida). Cosmético, pero confunde.

### 🟠 Seguridad — importante pero no bloqueante

- `SECRET_KEY` con default hardcodeado en `core/config.py:32` — mitigado por una guarda que
  aborta el arranque si `ENVIRONMENT` no es development/local, pero sigue siendo un secreto de
  valor conocido en el código versionado.
- ~~Imágenes Docker sin pin~~, ~~CSP laxa del frontend~~, ~~`/assets/` sin headers~~,
  ~~`python-jose`~~ y ~~`/health/detailed`~~: resueltos en la Ronda 10 (ver arriba).
- Cifrado en reposo solo cubre secretos puntuales (TOTP, password SMTP vía Fernet) — el
  contenido de archivos de usuario en MinIO no tiene SSE aplicado por la aplicación.
- `AuditLog` solo cubre POST/PUT/PATCH/DELETE — lecturas y descargas de archivos no dejan
  rastro; un acceso indebido de solo lectura no es detectable vía auditoría.
- Consola de MinIO de dev expuesta en `0.0.0.0:58103` con credenciales de desarrollo en texto
  plano en el compose — aceptable solo si la máquina no es alcanzable desde LAN/internet.
- Rate-limit de shares públicos (`files/router.py:719-732`) usa `request.client.host` directo
  — detrás de nginx en prod es un balde único compartido por todo el tráfico público, no limita
  por visitante real.
- ~~Menú ⋮ de la tabla de Archivos clippeado en la última fila~~ — corregido en la Ronda 10
  (portal + apertura hacia arriba + `maxHeight`), verificado en navegador a 4 alturas.
- Modal de subida: "Tamaño máximo" muestra bytes con sufijo MB (cosmético, sin corregir).

### 🧪 Testing — antes no existía nada

- Antes de la auditoría del 19: **0% de cobertura**, sin pytest ni vitest configurado en
  ningún lado del repo.
- Tras las Rondas 1-8: `filemeshy_back/tests/` (102 tests) + `filemeshy_back/requirements-dev.txt`
  — decidir si se incorporan al repo. Cubre: auth (registro, login, 2FA end-to-end), IDOR de
  archivos, carpetas, shares y versiones (copy, tags, compartir a usuario, escalación vía
  permission=edit, restore/purga de versiones), favoritos/orden con regresión explícita del bug
  de permisos, cuota propia y bajo versionado, CRUD de etiquetas con ownership, contraseña en
  links públicos, backfill de versiones vía migración, preview de video/audio por magic bytes,
  cache/invalidación/tamaño/rate-limit de preview de Office, indexación de contenido/OCR con
  regresión del bug de mappers del worker, escaneo de malware (EICAR) en los 4 puntos de
  entrada con regresión del bloqueo de event loop y del timeout no-total, backups de Postgres
  con verificación real en MinIO y RBAC por el camino real de asignación de rol (no bypass),
  administración de tenants (rate-limit, PATCH activar/desactivar con efecto real vía
  `TenantMiddleware`, validación de UUID), y regresión de los 3 fixes de seguridad más fáciles
  de reproducir automatizadamente (spoofing de IP, DoS 2FA, flag de registro).
- Tras la Ronda 10: **123 passed, 8 skipped, 0 failed**. Antes, tras la Ronda 9: 112 passed, 8 skipped, 0 failed, sin flakiness. Los 8 skipped siguen
  siendo `test_platform_tenants.py` completo (solo corren con `DEPLOYMENT_MODE=cloud` activo, ver
  Ronda 8). Suma de la Ronda 9: subida multipart de archivos grandes (sesiones, admisión global Y
  por usuario, cuota real contra tamaño verificado, resumabilidad vía `ListParts` real), antivirus
  asíncrono (limpio/infectado/`clamd` caído con reintentos, cuarentena real con liberación de
  cuota, streaming sin bufferizar el archivo completo).
- Última corrida (contra la imagen final reconstruida, backend Y `celery_worker`, modo `local`
  por defecto): **112 passed, 8 skipped, 0 failed**, reverificada de forma independiente por 3
  agentes en fases separadas de la Ronda 9 (implementación, auditor final, pruebas).
- Falta: tests de frontend (cero — cada ronda se verificó visualmente a mano con Playwright
  ad-hoc, no queda como suite automatizada), tests de aislamiento multi-tenant más allá de los
  de la Ronda 8, CI que corra esto automáticamente (no hay ningún pipeline en el repo), y los
  gaps de cobertura puntuales que dejó documentados la Ronda 9 (ver esa sección: camino
  fail-closed del escaneo AV no ejercitado de punta a punta, streaming de MinIO→clamd sin
  assert programático, tope global de admisión sin test en aislamiento).

### 📋 Funcionalidades de producto — gaps priorizados (vs. `docs/checklist-funcionalidades.md`)

**Resuelto en Ronda 1 (2026-09-20):** favoritos (archivo y carpeta, con ícono visible en fila
y grilla), ordenamiento real (nombre/tamaño/fecha, asc/desc, ya no hardcodeado), copiar
archivo/carpeta (recursivo, respeta cuota y profundidad máxima), cuota de almacenamiento
visible para el usuario final (`GET /storage-quotas/me` + widget en el Sidebar) y notificación
automática cuando el uso supera el 90% del límite (con deduplicación). Todo verificado en vivo
y visualmente en navegador, no solo en tests.

**Resuelto en Ronda 3 (2026-09-20):** notificación real al compartir un archivo/carpeta con un
usuario específico; compartir con permisos granulares (lectura/escritura) y a usuarios
específicos (además del link público de siempre); protección por contraseña en links públicos.
La única pieza de "colaboración" que sigue sin cubrir es comentar sobre un archivo (no
planificado en ninguna ronda todavía).

**Resuelto en Ronda 5 (2026-09-20):** vista previa de video y audio (reproducción nativa) y de
documentos de Office (conversión a PDF vía servicio aislado) — antes solo imagen/PDF.

**Resuelto en Ronda 6 (2026-09-21):** búsqueda por contenido de archivo (no solo nombre) y OCR
sobre imágenes y PDFs escaneados. Sin filtros avanzados (tipo, fecha, tamaño) en la página de
Archivos todavía, aunque el componente ya existe y se usa en otros módulos — queda como gap
menor, no planificado en ninguna ronda por ahora.

**Resuelto en Ronda 7 (2026-09-21):** escaneo de virus/malware en todo contenido nuevo subido
(ClamAV, fail-closed). Backup automático de Postgres, con verificación real y retención.

**Resuelto en Ronda 8 (2026-09-22):** UI de administración de tenants (multi-tenant), como
panel separado del admin normal — crear/listar/activar/desactivar/cambiar plan, protegido por
`X-Platform-Key`. Cierra el roadmap de construcción completo (rondas 1 a 8).

**Resuelto en Ronda 9 (2026-09-22, post-roadmap):** subida de archivos grandes (10-20GB) sin
saturar el servidor — multipart resumable directo a MinIO, antivirus asíncrono con gate de
visibilidad, admission control, sin necesidad de escalar horizontal ni verticalmente. Ver
narrativa completa más arriba.

Gaps que siguen abiertos:

1. **Parcialmente resuelto en Ronda 7:** el backup de MinIO (contenido de archivos) sigue sin
   cobertura real — la tarea existe pero requiere un destino S3 externo que hoy no está
   configurado en ningún entorno; hasta que se configure, los archivos de usuario NO tienen
   backup, solo sus metadatos en Postgres.
2. **Decisión de producto explícita, diferida sin fecha** (confirmado con el usuario
   2026-09-20): cliente de escritorio, app móvil, sincronización selectiva, acceso offline
   real y edición colaborativa en tiempo real quedan fuera del alcance actual del roadmap de
   construcción — no son un olvido, es una decisión tomada.
3. Formato de error inconsistente entre excepciones tipadas (`{status,message,data}`) y
   errores de validación Pydantic (`{"detail":[...]}`) — dos formatos conviven en la API
   (confirmado que el panel de plataforma de la Ronda 8 también usa el formato
   `{status,message,data}`, no es un caso aislado).

### 🏗️ Estándares técnicos — gaps priorizados (vs. `docs/estandares-cliente-servidor-2026/`)

1. Cero CI/CD — no hay pipeline (`.github/workflows` ni similar), nada corre lint/tests antes
   de mergear.
2. Sin SCA/escaneo de dependencias (Dependabot, `pip-audit`, `npm audit`).
3. Logging no estructurado (texto plano) y sin métricas/alertas — sin Prometheus, sin
   OpenTelemetry, sin dashboard de errores. Dos configuraciones de logging compitiendo
   (`main.py` vs `core/logging_config.py`). `RequestLoggingMiddleware` es código muerto
   (nunca se registra en `main.py`, lo dice su propio docstring).
4. Sin SLA/SLO, sin runbooks de incidentes, sin estrategia de rollback rápido (imágenes sin
   tag versionado — un rebuild sobreescribe `latest` sin dejar una versión previa conocida).
5. Ruff sin archivo de configuración versionado en el backend (existe `.ruff_cache/` pero no
   `pyproject.toml`/`ruff.toml`) — el lint no es reproducible ni forzado en CI (que tampoco existe).
6. Sin mypy/type-checking estático en backend (el frontend sí tiene TS estricto).
7. Sin exportación de datos ni cumplimiento GDPR/portabilidad; borrado de cuenta es
   hard-delete admin-only, sin flujo self-service.
8. Sin passkeys/WebAuthn (solo TOTP).
9. Healthchecks faltantes en `backend`/`celery_worker`/`frontend` de
   `docker-compose.prod.yml` (sí los tienen postgres/redis/minio).
10. Swagger/Redoc/OpenAPI solo se exponen si `DEBUG=True` — en producción no hay contrato
    de API consultable ni por el propio equipo.
11. ESLint del frontend no está limpio en baseline (confirmado en Ronda 8: 58 errores/8
    warnings preexistentes en todo `filemeshy_front/`, ninguno introducido por rondas de
    construcción) — mismo problema de fondo que el punto 5 (Ruff sin config forzada en
    backend), del lado frontend: sin gate en CI, la deuda de lint solo crece.

### 🐛 Bugs puntuales confirmados en vivo

- ~~`SUPER_ADMIN` con email `.local` queda bloqueado para login~~ — corregido en la Ronda 10:
  el script ahora rechaza el email antes de insertar. La cuenta `audit-test@wolfgrimm.local`
  del stack de prueba sigue existiendo y bloqueada (dato de prueba, se va con `down -v`).
- ~~Modo claro del tema~~ — no reproducible en el build actual (2026-09-25), ver Ronda 10.

### Notas operativas

- Stack de prueba (puertos 58100-58105) con datos de prueba propios en la base de datos
  (usuarios `qa-audit-user@example.com`, `idor-userA/B@example.com`, `pytest_*`,
  `auditor-*@example.com`, `smoketest-*@example.com`, y los admins `audit-admin@example.com`/
  `audit-test@wolfgrimm.local` — este último permanentemente bloqueado para login, ver bug
  puntual más abajo) — no es producción. Se puede tirar abajo con `docker compose down -v`
  cuando se quiera.
- Rondas 1 (`d91a47f`), 2 (`61ca9f1`), 3 (`9b08c35`), 4 (`7e9feba`), 5 (`a1c2680`), 6
  (`d833b83`), 7 (`05bd75f`) y 8 (`e76e197`) commiteadas, 2026-09-20/22. Ronda 9 (subida de
  archivos grandes) commiteada (`bcc90e0`). Ronda 10 (endurecimiento) commiteada `3ac8187` (2026-09-24), cierre y fix del Dropdown el 2026-09-25.
  Recordatorio operativo real (no solo de código): antes de considerar el permiso `backups.view`
  activo en cualquier entorno nuevo, hay que correr `scripts/seed_permissions.py` — agregar un
  permiso al dict de `permissions.py` no lo propaga solo a las tablas reales (bug real de la
  Ronda 7, ya corregido en este stack).
- El stack de prueba se cayó por reinicios del host varias veces durante el trabajo de las
  Rondas 2 a 7 — siempre se recuperó sin pérdida de código (todo en disco) ni de datos de
  prueba (volumen de Postgres persistente); solo hizo falta recrear el contenedor backend con
  `--force-recreate` (un error transitorio de permisos en el primer arranque en bloque tras
  cada reinicio, no un bug real).
- Para probar el panel de plataforma (Ronda 8) hace falta modo `DEPLOYMENT_MODE=cloud`, que
  este stack de dev/test NO usa por defecto (el resto de la app asume modo `local`). Se prueba
  con un `docker-compose.override.yml` puntual (gitignoreado, NUNCA comitear — ver el propio
  `.gitignore` para el motivo completo) con `DEPLOYMENT_MODE=cloud` + `PLATFORM_API_KEY`, y se
  saca del checkout al terminar de probar — dejarlo puesto rompe la suite completa y la app
  normal, porque en modo cloud `TenantMiddleware` exige `X-Tenant-Slug` en toda request.

### Roadmap de construcción (rondas siguientes, backlog completo)

Aprobado con el usuario el 2026-09-20. Cada ronda se diseña en detalle recién cuando le toca.

| Ronda | Contenido |
|---|---|
| 1 (hecho) | 6 bugs de seguridad + tenant provisioning + favoritos + orden real + copiar + cuota visible — **completa** |
| 2 (hecho) | Etiquetas (tags many-to-many) — **completa** |
| 3 (hecho) | Compartir granular (contraseña, permisos lectura/escritura, compartir a usuario específico) + notificaciones de "te compartieron algo" — **completa** |
| 4 (hecho) | Versionado de archivos (historial, restaurar versión anterior) — **completa** |
| 5 (hecho) | Preview extendido (video, audio, documentos de Office) — **completa** |
| 6 (hecho) | Búsqueda por contenido + OCR — **completa** |
| 7 (hecho) | Antivirus (ClamAV) en upload + backups automáticos de Postgres/MinIO — **completa** (MinIO condicional a config externa, ver Ronda 7 arriba) |
| 8 (hecho) | UI de administración de tenants — **completa**, roadmap original cerrado |
| 9 (hecho) | Post-roadmap, pedido explícito del usuario 2026-09-22: subida de archivos grandes (10-20GB) sin saturar el servidor, resumable — **completa** |
| 10 (hecho y verificado en vivo) | Endurecimiento: `Retry-After`, PyJWT, pin por digest, CSP, headers de `/assets/`, `/health/detailed`, validación de email del super admin, portal del Dropdown, tests de Ronda 9 |

Fuera de alcance por decisión de producto (no construir sin pedido explícito nuevo): cliente
de escritorio, app móvil, sincronización selectiva, acceso offline real, edición colaborativa
en tiempo real.

### Semáforo

**Roadmap original completo (Rondas 1-8) + Ronda 9 post-roadmap, todas verificadas en vivo**
(incluida verificación visual en navegador real, y desde Ronda 3 en adelante, reproducción de
escenarios de punta a punta por el propio Auditor Final, incluida verificación de contenido
real —no solo capturas— en las Rondas 5, 6, 7, 8 y 9). Listo para uso interno de un solo
usuario/equipo pequeño en red cerrada — los 6 bloqueadores de seguridad de la auditoría del 19
están resueltos, y el Drive ganó favoritos, orden real, copiar, cuota visible, etiquetas,
compartir granular (contraseña, permisos, usuarios específicos) con notificaciones reales,
versionado de archivos con historial completo, preview de video/audio/Office, búsqueda por
contenido + OCR, escaneo de malware en toda subida, backups automáticos de Postgres con
verificación real, administración de tenants multi-tenant vía panel separado, y subida de
archivos grandes (10-20GB) resumable y sin saturar el servidor con antivirus asíncrono. **Todavía
no listo para exposición pública a Internet sin decisión** sobre las deudas residuales de
seguridad marcadas arriba en cada ronda (todas confirmadas no explotables hoy, pero dependen de
configuración de producción que este repo de trabajo no controla directamente, de defensa en
profundidad pendiente, o de contratar un destino externo): `TRUSTED_PROXY_IPS` vacío en
producción real, el balde compartido de rate-limit en shares públicos, la falta de rate-limit en
los endpoints autenticados de shares dirigidos, la red no dedicada de los servicios
`office_converter` y `clamav`, la falta de tope de páginas/reintentos en la indexación de PDFs de
texto embebido, la ausencia de backup real de los archivos de usuario en MinIO (solo sus
metadatos) hasta que se configure un destino S3 externo, la ausencia de sesión/expiración/
auditoría real en el panel de plataforma de la Ronda 8 (hoy solo la propia key, sin capa
adicional), y el header `Retry-After` que el backend nunca logra entregar en ningún 503 con
headers custom (bug preexistente, expuesto por la Ronda 9, mitigado del lado frontend pero no
corregido de raíz).

**Patrón recurrente confirmado en 6 de las últimas 7 rondas, siempre atrapado por el propio
proceso antes de cerrar la ronda, nunca por pytest solo:** un bug de "código que funciona en el
proceso de tests pero se rompe en el proceso/entorno real" (Ronda 4: `celery_worker` con imagen
vieja; Ronda 5: contrato roto solo visible contra el backend real; Ronda 6: registro de mappers
de SQLAlchemy envenenado según el orden de tareas en el worker real; Ronda 7: un permiso nuevo
en el código que nunca se sembró en la tabla real, invisible para tests que usan un bypass
directo de BD en vez del camino real de asignación de rol; Ronda 8: un campo (`admin_email`)
descartado en silencio por el schema de respuesta, y una `tenant_id` sin tipar que solo
explotaba con un valor real malformado; Ronda 9: tres bugs de firma SigV4 en el proxy de nginx,
ninguno visible probando la firma o nginx por separado, solo contra el proxy real completo, más
un modal de UI bloqueado que ningún test automatizado iba a atrapar — solo apareció al navegar
de verdad con una subida real en curso). Todos aparecieron recién al probar contra el stack
Docker completo levantado, con datos y flujos reales. Confirma que la verificación en vivo (no
solo tests unitarios/aislados, y no solo tests que "pasan" sin ejercitar el camino real que usa
un usuario de verdad) sigue siendo imprescindible antes de cerrar cualquier ronda futura.

**Lección de proceso confirmada en Ronda 4** (ya aplicada, dejar como recordatorio para
rondas futuras y para cualquier deploy real): reconstruir solo `backend` no alcanza cuando el
cambio toca código que también importa `celery_worker` — hay que reconstruir/recrear todos los
servicios que comparten ese código, y verificarlo explícitamente (no asumirlo) antes de dar una
ronda por desplegada.
