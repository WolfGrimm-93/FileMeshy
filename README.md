[English](README.md) | [Español](README.es.md)

# FileMeshy

Personal file storage and management, Google Drive style: nested folders and file explorer,
trash with restore, share links with expiry/revocation and optional password, per-user sharing
with read/write permissions, tags, favorites, file versioning, inline preview (images, PDF,
video, audio, Office documents), full-text search with OCR, per-user storage quota, resumable
uploads of very large files (10-20 GB), antivirus scanning (ClamAV), automatic database
backups, multi-tenant administration, and complete role/permission (RBAC) authentication
(2FA, multiple sessions, token rotation).

Backend in FastAPI + PostgreSQL, frontend in React + Vite + TypeScript, file storage through
MinIO (S3-compatible), background jobs with Celery + Redis.

## Installation

Requirement: [Docker](https://docs.docker.com/get-docker/) and Docker Compose.

```bash
git clone <this-repo-url>
cd FileMeshy
docker compose up --build -d
```

This starts the whole stack (backend, frontend, PostgreSQL, Redis, MinIO, ClamAV, Office
converter, Celery worker) with development credentials already configured — no `.env` needed.

| Service | URL |
|---|---|
| Frontend | http://localhost:58100 |
| Backend / API | http://localhost:58101/api/v1 (interactive docs at `/docs`, only when `DEBUG=True`) |
| MinIO console | http://localhost:58103 |

Migrations run automatically when the backend starts. You still need to seed roles/permissions
and create the first user:

```bash
docker compose exec backend python scripts/seed_permissions.py
printf '%s' 'your-password' | docker compose exec -T backend python scripts/create_super_admin.py your-email@example.com
```

The email must be valid for login: reserved domains (`.local`, `.test`, `.invalid`,
`.localhost`, `.onion`, `.arpa`) are rejected. Then open http://localhost:58100 with that user.

## Operational notes

- Any change to shared code (`app/files`, `app/worker`, ...) requires rebuilding **every**
  service that imports it (`backend` **and** `celery_worker`), not just one.
- Docker base images are pinned by digest; update the digests by hand periodically to receive
  security patches.
- The frontend CSP allows one inline script by SHA-256 hash (see `filemeshy_front/nginx.conf`);
  if the inline script in `index.html` changes, recompute the hash.
- Tests: backend `docker compose exec backend python -m pytest tests` (needs the stack running and pytest from `requirements-dev.txt`); frontend `pnpm test` in `filemeshy_front/`. CI (`.github/workflows/ci.yml`) runs lint, type-check, frontend tests, build and dependency audit.
- Behind a reverse proxy set `TRUSTED_PROXY_IPS` (IPs or CIDR) so rate limiting and audit logs use the real client IP; `TRUSTED_PROXY_IP_HEADERS` (default `["x-real-ip"]`) chooses which header to trust. See [docs/operacion.md](docs/operacion.md) (Spanish).
- File contents in MinIO are **not** backed up unless an external S3-compatible destination is
  configured (`BACKUP_S3_*` variables). Only the PostgreSQL database is backed up by default.

## Documentation

- [Backlog and project log](pendiente.md) — round-by-round history, known debt and open items (Spanish).
- [Brand guidelines](docs/brand-guidelines.md) — palette, typography, logo usage.
- [Feature checklist](docs/checklist-funcionalidades.md) — Google Drive-like product scope.
- [Modules](docs/modulos/index.md) — the checklist above broken down by product module.
- [Client-Server Standards 2026](docs/estandares-cliente-servidor-2026/index.md) — technical quality checklist (architecture, security, frontend, etc.), not product features.
