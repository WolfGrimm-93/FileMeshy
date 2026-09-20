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

### 🟠 Seguridad — importante pero no bloqueante

- `SECRET_KEY` con default hardcodeado en `core/config.py:32` — mitigado por una guarda que
  aborta el arranque si `ENVIRONMENT` no es development/local, pero sigue siendo un secreto de
  valor conocido en el código versionado.
- Imágenes Docker sin pin de versión/digest (`postgres:15-alpine`, `redis:7-alpine`,
  `node:22-alpine`, `python:3.11-slim`) — riesgo de reproducibilidad y de traer CVEs sin aviso.
- CSP del frontend (`filemeshy_front/nginx.conf`) mucho más laxa que la del backend — solo
  `frame-ancestors 'none'`, sin `default-src`/`script-src` restrictivo.
- `nginx.conf` — el location `/assets/` pierde 3 de los 4 headers de seguridad
  (`X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy`) por un bug de herencia de
  `add_header` por location; confirmado en vivo con curl. Contradice la intención documentada
  en el propio comentario del archivo.
- `python-jose==3.3.0` sin mantenimiento activo, con CVE-2024-33663/33664 — mitigado porque se
  fuerza `algorithms=["HS256"]` explícito al decodificar, pero conviene migrar a `pyjwt`/`authlib`.
- Cifrado en reposo solo cubre secretos puntuales (TOTP, password SMTP vía Fernet) — el
  contenido de archivos de usuario en MinIO no tiene SSE aplicado por la aplicación.
- `AuditLog` solo cubre POST/PUT/PATCH/DELETE — lecturas y descargas de archivos no dejan
  rastro; un acceso indebido de solo lectura no es detectable vía auditoría.
- Compartir por link público: sin protección por contraseña, ni en API (`ShareCreate` no tiene
  el campo) ni en UI — no es un bypass, es una feature no implementada. Si se manda un campo
  `password` igual da 201 (se ignora silenciosamente).
- `/health/detailed` (bien gateado a rol admin) expone versión detallada de Postgres/Python y
  el flag `debug:true` — innecesario para un healthcheck, reducir el payload.
- Sin escaneo de virus/malware en archivos subidos — solo se valida tipo por magic bytes, no
  contenido malicioso.
- Consola de MinIO de dev expuesta en `0.0.0.0:58103` con credenciales de desarrollo en texto
  plano en el compose — aceptable solo si la máquina no es alcanzable desde LAN/internet.
- Rate-limit de shares públicos (`files/router.py:719-732`) usa `request.client.host` directo
  — detrás de nginx en prod es un balde único compartido por todo el tráfico público, no limita
  por visitante real.

### 🧪 Testing — antes no existía nada

- Antes de la auditoría del 19: **0% de cobertura**, sin pytest ni vitest configurado en
  ningún lado del repo.
- Tras la Ronda 1: `filemeshy_back/tests/` (25 tests) + `filemeshy_back/requirements-dev.txt`
  — **sigue sin commitear**, decidir si se incorporan al repo. Cubre: auth (registro, login,
  2FA end-to-end), IDOR de archivos y carpetas (incluido copy), favoritos/orden con
  regresión explícita del bug de permisos, cuota propia, y regresión de los 3 fixes de
  seguridad más fáciles de reproducir automatizadamente (spoofing de IP, DoS 2FA, flag de
  registro).
- Última corrida (contra la imagen final reconstruida, dos veces seguidas): **25 passed, 0
  failed**, sin flakiness.
- Falta: tests de frontend (cero — la Ronda 1 se verificó visualmente a mano con Playwright
  ad-hoc, no queda como suite automatizada), tests de aislamiento multi-tenant, y CI que
  corra esto automáticamente (no hay ningún pipeline en el repo).

### 📋 Funcionalidades de producto — gaps priorizados (vs. `docs/checklist-funcionalidades.md`)

**Resuelto en Ronda 1 (2026-09-20):** favoritos (archivo y carpeta, con ícono visible en fila
y grilla), ordenamiento real (nombre/tamaño/fecha, asc/desc, ya no hardcodeado), copiar
archivo/carpeta (recursivo, respeta cuota y profundidad máxima), cuota de almacenamiento
visible para el usuario final (`GET /storage-quotas/me` + widget en el Sidebar) y notificación
automática cuando el uso supera el 90% del límite (con deduplicación). Todo verificado en vivo
y visualmente en navegador, no solo en tests.

Gaps que siguen abiertos, ver roadmap de rondas al final del archivo:

1. **Notificaciones de producto para compartir/modificar archivo** — solo se conectó la de
   cuota (Ronda 1). Compartir/comentar/modificar todavía no disparan nada porque hoy no existe
   un destinatario real (el share es anónimo) — queda planificado para la Ronda 3, junto con
   el compartir granular que le da sentido a esta notificación.
2. Compartir es solo por link público de **solo lectura** — sin compartir a usuarios
   específicos, sin permisos granulares (lectura/escritura/comentar), sin protección por
   contraseña. Es el corazón de "colaboración" y hoy es la parte más débil del checklist.
   Planificado: Ronda 3.
3. Sin backups automáticos de Postgres/MinIO — cero rastro en todo el repo, ni siquiera un
   cron de `pg_dump`. Planificado: Ronda 7.
4. Sin versionado de archivos (historial de cambios) — ni modelo ni concepto en el código.
   Planificado: Ronda 4.
5. **Decisión de producto explícita, diferida sin fecha** (confirmado con el usuario
   2026-09-20): cliente de escritorio, app móvil, sincronización selectiva, acceso offline
   real y edición colaborativa en tiempo real quedan fuera del alcance actual del roadmap de
   construcción — no son un olvido, es una decisión tomada.
6. Sin etiquetas/categorías. Planificado: Ronda 2.
7. Multi-tenant real a nivel de datos (schema-per-tenant, bien implementado, activo solo si
   `DEPLOYMENT_MODE=cloud`) pero sin ninguna UI de gestión — solo utilizable vía CLI/API
   interna, no es autoservicio hoy. Planificado: Ronda 8.
8. Búsqueda solo por nombre, no por contenido de archivo. Sin filtros avanzados (tipo, fecha,
   tamaño) en la página de Archivos, aunque el componente ya existe y se usa en otros módulos.
   Búsqueda por contenido + OCR planificados: Ronda 6 (confirmado en alcance con el usuario).
9. Vista previa solo de imagen/PDF — video, audio y documentos de Office fuerzan descarga.
   Planificado: Ronda 5.
10. Formato de error inconsistente entre excepciones tipadas (`{status,message,data}`) y
    errores de validación Pydantic (`{"detail":[...]}`) — dos formatos conviven en la API.
11. Sin escaneo de virus/malware. Planificado: Ronda 7.

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

### 🐛 Bugs puntuales confirmados en vivo

- Un `SUPER_ADMIN` creado con un email de dominio no resoluble en DNS real (ej. `.local`)
  queda **permanentemente bloqueado para loguearse** — `EmailStr` de Pydantic hace
  deliverability check en `/auth/login`, pero `scripts/create_super_admin.py` no valida esto
  al crear la cuenta (inserta directo en la BD). Documentar en el script/README que el email
  debe ser de un dominio con DNS real, o relajar esa validación para login.

### Notas operativas

- Stack de prueba (puertos 58100-58105) con datos de prueba propios en la base de datos
  (usuarios `qa-audit-user@example.com`, `idor-userA/B@example.com`, `pytest_*`,
  `auditor-*@example.com`, `smoketest-*@example.com`, y los admins `audit-admin@example.com`/
  `audit-test@wolfgrimm.local` — este último permanentemente bloqueado para login, ver bug
  puntual más abajo) — no es producción. Se puede tirar abajo con `docker compose down -v`
  cuando se quiera.
- Suite de tests (`filemeshy_back/tests/`, `filemeshy_back/requirements-dev.txt`) sigue en el
  working tree sin commitear — pendiente decidir si se incorpora al repo.
- Todo el código de la Ronda 1 (backend + frontend) está en el working tree, sin commitear
  todavía — pendiente confirmación explícita del usuario antes de commitear (regla del
  proyecto: nunca commitear sin pedido explícito).

### Roadmap de construcción (rondas siguientes, backlog completo)

Aprobado con el usuario el 2026-09-20. Cada ronda se diseña en detalle recién cuando le toca.

| Ronda | Contenido |
|---|---|
| 1 (hecho) | 6 bugs de seguridad + tenant provisioning + favoritos + orden real + copiar + cuota visible — **completa** |
| 2 | Etiquetas (tags many-to-many) |
| 3 | Compartir granular (contraseña, permisos lectura/escritura, compartir a usuario específico) + notificaciones de "te compartieron algo" |
| 4 | Versionado de archivos (historial, restaurar versión anterior) |
| 5 | Preview extendido (video, audio, documentos de Office) |
| 6 | Búsqueda por contenido + OCR |
| 7 | Antivirus (ClamAV) en upload + backups automáticos de Postgres/MinIO |
| 8 | UI de administración de tenants |

Fuera de alcance por decisión de producto (no construir sin pedido explícito nuevo): cliente
de escritorio, app móvil, sincronización selectiva, acceso offline real, edición colaborativa
en tiempo real.

### Semáforo

**Ronda 1 completa y verificada en vivo** (incluida verificación visual en navegador real).
Listo para uso interno de un solo usuario/equipo pequeño en red cerrada — los 6 bloqueadores
de seguridad de la auditoría del 19 están resueltos. **Todavía no listo para exposición
pública a Internet sin decisión** sobre las 2 deudas residuales marcadas arriba
(`TRUSTED_PROXY_IPS` en producción real, y el balde compartido de rate-limit en shares
públicos) — ninguna es explotable hoy, pero ambas dependen de configuración de producción que
este repo de trabajo no controla directamente.
