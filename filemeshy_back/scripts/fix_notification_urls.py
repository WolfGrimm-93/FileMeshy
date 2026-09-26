"""Un solo uso (Ronda 12b): corrige `notifications.action_url` históricas que
apuntan a rutas inexistentes del frontend (ver app/notifications/routes.py).
Idempotente (una segunda corrida no cambia nada) y con --dry-run.

    docker compose exec -T backend python scripts/fix_notification_urls.py --dry-run
    docker compose exec -T backend python scripts/fix_notification_urls.py
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.core.database import SessionLocal
from app.notifications.routes import LEGACY_ACTION_URL_MAP


def fix_notification_urls(*, dry_run: bool, db=None, schema=None) -> dict:
    """Devuelve {url_vieja: filas_afectadas}. `schema`: schema de tenant (modo cloud)."""
    own = db is None
    if own and schema is not None:
        from app.core.database import tenant_schema_ctx

        token = tenant_schema_ctx.set(schema)
    else:
        token = None
    db = db or SessionLocal()
    try:
        result = {}
        for old, new in LEGACY_ACTION_URL_MAP.items():
            if dry_run:
                n = db.execute(text("SELECT count(*) FROM notifications WHERE action_url = :o"), {"o": old}).scalar_one()
            else:
                n = db.execute(
                    text("UPDATE notifications SET action_url = :n WHERE action_url = :o"), {"n": new, "o": old}
                ).rowcount
            result[old] = n
        if not dry_run:
            db.commit()
        return result
    finally:
        if own:
            db.close()
        if token is not None:
            from app.core.database import tenant_schema_ctx

            tenant_schema_ctx.reset(token)


def fix_notification_urls_all_schemas(*, dry_run: bool, schemas=None) -> dict:
    """Recorre `iter_tenant_schemas()` (modo local: un único schema por defecto) y suma los
    totales por URL vieja."""
    from app.worker.db import iter_tenant_schemas

    total = {old: 0 for old in LEGACY_ACTION_URL_MAP}
    for schema in (schemas if schemas is not None else iter_tenant_schemas()):
        for old, n in fix_notification_urls(dry_run=dry_run, schema=schema).items():
            total[old] += n
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--schema", default=None, help="schema de tenant (modo cloud); por defecto public")
    parser.add_argument(
        "--all-schemas", action="store_true",
        help="todos los tenants activos (modo cloud); sin esto, en modo cloud solo se procesa public (o --schema)",
    )
    args = parser.parse_args()
    if args.all_schemas and args.schema:
        parser.error("--all-schemas y --schema son excluyentes")
    if args.all_schemas:
        res = fix_notification_urls_all_schemas(dry_run=args.dry_run)
    else:
        res = fix_notification_urls(dry_run=args.dry_run, schema=args.schema)
    print(("[DRY-RUN] " if args.dry_run else "") + ", ".join(f"{k} -> {LEGACY_ACTION_URL_MAP[k]}: {v}" for k, v in res.items()))
