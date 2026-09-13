# FileMeshy

Almacenamiento y gestión de archivos personal, tipo Google Drive: explorador de archivos y
carpetas anidadas, papelera con restauración, compartir por link con expiración/revocación,
preview inline de imágenes y PDF, cuota de almacenamiento por usuario, y autenticación con
roles y permisos (RBAC) completa (2FA, sesiones múltiples, rotación de tokens).

Backend en FastAPI + PostgreSQL, frontend en React + Vite + TypeScript, almacenamiento de
archivos vía MinIO (compatible con S3).

## Instalación

Requisito: [Docker](https://docs.docker.com/get-docker/) y Docker Compose.

```bash
git clone <url-de-este-repo>
cd FileMeshy
docker compose up --build -d
```

Levanta todo el stack (backend, frontend, PostgreSQL, Redis, MinIO) con credenciales de
desarrollo ya configuradas — no hace falta crear ningún `.env`.

| Servicio | URL |
|---|---|
| Frontend | http://localhost:58100 |
| Backend / API | http://localhost:58101/api/v1 (docs interactivas en `/docs`) |
| Consola MinIO | http://localhost:58103 |

Las migraciones corren solas al iniciar el backend. Falta sembrar roles/permisos y crear el
primer usuario:

```bash
docker compose exec backend python scripts/seed_permissions.py
printf '%s' 'tu-contraseña' | docker compose exec -T backend python scripts/create_super_admin.py tu-email@ejemplo.com
```

Listo — entrá a http://localhost:58100 con ese usuario.

## Documentación

- [Guía de marca](docs/brand-guidelines.md) — paleta, tipografía, uso del logo.
- [Checklist de funcionalidades](docs/checklist-funcionalidades.md) — alcance de producto tipo Google Drive.
- [Módulos](docs/modulos/index.md) — el checklist anterior desglosado por módulo de producto.
- [Estándares Cliente-Servidor 2026](docs/estandares-cliente-servidor-2026/index.md) — checklist de calidad técnica (arquitectura, seguridad, frontend, etc.), no funcionalidades de producto.
