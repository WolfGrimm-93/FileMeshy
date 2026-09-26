"""Un solo uso (Ronda 12): rescata las filas LEGADAS de `file_content_index`
que quedaron en 'pending' con `attempted_at IS NULL`.

Contexto: antes de que `register_attempt` seteara `attempted_at`, una tarea
`index_file_content` que nunca llegó a correr (worker caído al encolar, tarea
perdida) dejaba la fila en 'pending' SIN marca de tiempo. El barrido periódico
de huérfanas (app/worker/tasks/maintenance.py) solo mira filas con
`attempted_at` no nulo y vencido, así que esas filas no las toca nadie. El
código actual ya no puede generar más.

Qué hace, por cada fila 'pending' con `attempted_at IS NULL`:
  - Archivo existente y NO borrado (`deleted_at IS NULL`): resetea `attempts=0`
    y RE-ENCOLA `index_file_content`. Al correr, `register_attempt` setea
    `attempted_at`, y desde ahí el barrido normal cubre si la tarea vuelve a
    morir.
  - Archivo inexistente o borrado: marca la fila 'failed' con un mensaje claro
    (nada que indexar).

Idempotente: una segunda corrida solo ve lo que siga pendiente sin
`attempted_at` (p. ej. tareas re-encoladas que el worker todavía no tomó, que
se re-encolan otra vez sin daño -- `register_attempt` es atómico). `--dry-run`
solo informa, no cambia nada ni encola.

SQL directo (Core) para las lecturas/escrituras, mismo criterio que
scripts/seed_permissions.py (no depender del grafo de mappers ORM en un
proceso standalone).

Uso:
    docker compose exec -T backend python scripts/reindex_legacy_pending.py --dry-run
    docker compose exec -T backend python scripts/reindex_legacy_pending.py
    # modo cloud: un schema de tenant puntual
    docker compose exec -T backend python scripts/reindex_legacy_pending.py --schema tenant_xxx
    # modo cloud: TODOS los tenants activos (en modo local equivale al schema por defecto)
    docker compose exec -T backend python scripts/reindex_legacy_pending.py --all-schemas

OJO: sin `--all-schemas` ni `--schema`, en modo cloud solo se procesa el schema
por defecto (public), NO los de los tenants.
"""
import argparse
import sys
from pathlib import Path
from typing import Callable, Iterable, Optional
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.worker.db import get_worker_db

MSG_FILE_MISSING = "Archivo inexistente o eliminado: no hay contenido que indexar (limpieza de fila legada)"


def _default_enqueue(schema: Optional[str], file_id: str) -> None:
    from app.worker.tasks.indexing import index_file_content

    index_file_content.delay(schema, file_id)


def reindex_legacy_pending(
    *,
    dry_run: bool,
    schema: Optional[str] = None,
    enqueue: Optional[Callable[[Optional[str], str], None]] = None,
    only_file_ids: Optional[Iterable[UUID]] = None,
) -> dict:
    """Devuelve `{"found", "requeued", "failed", "enqueue_errors"}`.
    `enqueue` y `only_file_ids` existen para los tests (no se usan por CLI)."""
    enqueue = enqueue or _default_enqueue
    only = [str(f) for f in only_file_ids] if only_file_ids is not None else None
    result = {"found": 0, "requeued": 0, "failed": 0, "enqueue_errors": 0}

    with get_worker_db(schema_name=schema) as db:
        query = (
            "SELECT i.file_id, (f.id IS NOT NULL AND f.deleted_at IS NULL) AS alive "
            "FROM file_content_index i LEFT JOIN files f ON f.id = i.file_id "
            "WHERE i.extraction_status = 'pending' AND i.attempted_at IS NULL"
        )
        params: dict = {}
        if only is not None:
            query += " AND CAST(i.file_id AS text) = ANY(:only)"
            params["only"] = only
        rows = db.execute(text(query), params).all()
        result["found"] = len(rows)

        alive_ids = [str(r[0]) for r in rows if r[1]]
        dead_ids = [str(r[0]) for r in rows if not r[1]]
        result["failed"] = len(dead_ids)
        result["requeued"] = len(alive_ids)

        if dry_run:
            return result

        if dead_ids:
            db.execute(
                text(
                    "UPDATE file_content_index SET extraction_status = 'failed', "
                    "error_message = :msg, indexed_at = now(), attempted_at = now() "
                    "WHERE CAST(file_id AS text) = ANY(:ids) "
                    "AND extraction_status = 'pending' AND attempted_at IS NULL"
                ),
                {"msg": MSG_FILE_MISSING, "ids": dead_ids},
            )
        if alive_ids:
            db.execute(
                # Mismo guard que el UPDATE de las filas muertas: si un worker tomó la
                # fila entre el SELECT y este UPDATE (register_attempt ya seteó
                # attempted_at), no se le resetea el contador.
                text(
                    "UPDATE file_content_index SET attempts = 0 "
                    "WHERE CAST(file_id AS text) = ANY(:ids) "
                    "AND extraction_status = 'pending' AND attempted_at IS NULL"
                ),
                {"ids": alive_ids},
            )
        db.commit()

        # Encolar DESPUÉS del commit: el worker tiene que ver la fila ya reseteada.
        for file_id in alive_ids:
            try:
                enqueue(schema, file_id)
            except Exception as exc:  # una tarea que no encola no frena a las demás
                result["enqueue_errors"] += 1
                result["requeued"] -= 1
                print(f"  ! no se pudo encolar {file_id}: {exc}", file=sys.stderr)
    return result


def reindex_all_schemas(*, dry_run: bool, enqueue=None, schemas: Optional[Iterable[Optional[str]]] = None) -> dict:
    """Corre `reindex_legacy_pending` por cada schema de `iter_tenant_schemas()`
    (modo local: un único None = schema por defecto). `schemas` solo para tests.
    Devuelve los totales sumados más `per_schema`."""
    from app.worker.db import iter_tenant_schemas

    total = {"found": 0, "requeued": 0, "failed": 0, "enqueue_errors": 0, "per_schema": {}}
    for schema in (schemas if schemas is not None else iter_tenant_schemas()):
        res = reindex_legacy_pending(dry_run=dry_run, schema=schema, enqueue=enqueue)
        total["per_schema"][schema or "public"] = res
        for key in ("found", "requeued", "failed", "enqueue_errors"):
            total[key] += res[key]
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="solo informar, no cambiar ni encolar nada")
    parser.add_argument("--schema", default=None, help="schema de tenant (modo cloud); por defecto public")
    parser.add_argument(
        "--all-schemas",
        action="store_true",
        help="procesar TODOS los tenants activos (modo cloud); sin esto, en modo cloud solo se procesa "
        "public (o el --schema indicado). En modo local equivale al schema por defecto.",
    )
    args = parser.parse_args()
    if args.all_schemas and args.schema:
        parser.error("--all-schemas y --schema son excluyentes")

    if args.all_schemas:
        res = reindex_all_schemas(dry_run=args.dry_run)
    else:
        res = reindex_legacy_pending(dry_run=args.dry_run, schema=args.schema)
    prefix = "[DRY-RUN] " if args.dry_run else ""
    print(
        f"{prefix}filas legadas pending sin attempted_at: {res['found']} | "
        f"a re-encolar: {res['requeued']} | a marcar failed (archivo inexistente/borrado): {res['failed']}"
        + (f" | errores al encolar: {res['enqueue_errors']}" if res["enqueue_errors"] else "")
    )
    return 1 if res["enqueue_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
