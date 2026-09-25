[English](README.md) | [Español](README.es.md)

# FileMeshy

Almacenamiento y gestión de archivos personal, tipo Google Drive: explorador de archivos y
carpetas anidadas, papelera con restauración, compartir por link con expiración/revocación y
contraseña opcional, compartir con usuarios específicos con permisos de lectura/escritura,
etiquetas, favoritos, versionado de archivos, preview inline (imágenes, PDF, video, audio y
documentos de Office), búsqueda por contenido con OCR, cuota de almacenamiento por usuario,
subida resumable de archivos muy grandes (10-20 GB), antivirus (ClamAV), backups automáticos de
la base de datos, administración multi-tenant, y autenticación con roles y permisos (RBAC)
completa (2FA, sesiones múltiples, rotación de tokens).

Backend en FastAPI + PostgreSQL, frontend en React + Vite + TypeScript, almacenamiento de
archivos vía MinIO (compatible con S3), tareas en segundo plano con Celery + Redis.

## Instalación

Requisito: [Docker](https://docs.docker.com/get-docker/) y Docker Compose.

```bash
git clone <url-de-este-repo>
cd FileMeshy
docker compose up --build -d
```

Levanta todo el stack (backend, frontend, PostgreSQL, Redis, MinIO, ClamAV, conversor de
Office, worker de Celery) con credenciales de desarrollo ya configuradas — no hace falta crear
ningún `.env`.

| Servicio | URL |
|---|---|
| Frontend | http://localhost:58100 |
| Backend / API | http://localhost:58101/api/v1 (docs interactivas en `/docs`, solo con `DEBUG=True`) |
| Consola MinIO | http://localhost:58103 |

Las migraciones corren solas al iniciar el backend. Falta sembrar roles/permisos y crear el
primer usuario:

```bash
docker compose exec backend python scripts/seed_permissions.py
printf '%s' 'tu-contraseña' | docker compose exec -T backend python scripts/create_super_admin.py tu-email@ejemplo.com
```

El email tiene que ser válido para el login: los dominios reservados (`.local`, `.test`,
`.invalid`, `.localhost`, `.onion`, `.arpa`) se rechazan. Listo — entrá a http://localhost:58100
con ese usuario.

## Notas operativas

- Cualquier cambio a código compartido (`app/files`, `app/worker`, ...) exige reconstruir
  **todos** los servicios que lo importan (`backend` **y** `celery_worker`), no solo uno.
- Las imágenes base de Docker están fijadas por digest; hay que actualizar los digests a mano
  de forma periódica para recibir parches de seguridad.
- La CSP del frontend permite un script inline por hash SHA-256 (ver
  `filemeshy_front/nginx.conf`); si cambia el script inline de `index.html`, hay que recalcular
  el hash.
- Tests: backend `docker compose exec backend python -m pytest tests` (requiere el stack levantado y pytest de `requirements-dev.txt`); frontend `pnpm test` en `filemeshy_front/`. El CI (`.github/workflows/ci.yml`) corre lint, type-check, tests de frontend, build y auditoría de dependencias.
- Detrás de un reverse proxy configurá `TRUSTED_PROXY_IPS` (IPs o CIDR) para que el rate-limit y la auditoría usen la IP real del cliente; `TRUSTED_PROXY_IP_HEADERS` (default `["x-real-ip"]`) elige en qué header confiar. Ver [docs/operacion.md](docs/operacion.md).
- El contenido de los archivos en MinIO **no** tiene backup salvo que se configure un destino
  S3-compatible externo (variables `BACKUP_S3_*`). Por defecto solo se respalda la base de datos
  PostgreSQL.

## Documentación

- [Pendientes y bitácora del proyecto](pendiente.md) — historial por ronda, deuda conocida y pendientes abiertos.
- [Guía de marca](docs/brand-guidelines.md) — paleta, tipografía, uso del logo.
- [Checklist de funcionalidades](docs/checklist-funcionalidades.md) — alcance de producto tipo Google Drive.
- [Módulos](docs/modulos/index.md) — el checklist anterior desglosado por módulo de producto.
- [Estándares Cliente-Servidor 2026](docs/estandares-cliente-servidor-2026/index.md) — checklist de calidad técnica (arquitectura, seguridad, frontend, etc.), no funcionalidades de producto.
