"""
Utilidad para reparar texto con encoding corrupto (mojibake) en la base de datos.

Tipos de corrupción soportados:
  1. CP437 mojibake: bytes UTF-8 decodificados como CP437 → ├│ en vez de ó
  2. Latin-1 mojibake: bytes UTF-8 decodificados como Latin-1 → Ã³ en vez de ó

Uso:
  cd filemeshy_back
  python -m app.shared.utils.fix_mojibake            # modo simulación (dry-run)
  python -m app.shared.utils.fix_mojibake --apply    # aplica cambios reales
"""

import sys
import re
from sqlalchemy import text
from app.core.database import SessionLocal

# Forzar UTF-8 en la salida del terminal (Windows)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# Detecta si el string tiene caracteres que indican mojibake
BOX_DRAWING_RE = re.compile(r'[─-╿]')          # CP437 mojibake: ├│┬╞╗...
LATIN1_MOJIBAKE_RE = re.compile(r'[À-ÿ]{2,}')  # Latin-1 mojibake: Ã³Ã©...


def fix_cp437(text_value: str) -> str:
    """Repara mojibake tipo CP437 (├│ → ó)."""
    try:
        return text_value.encode('cp437').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text_value


def fix_latin1(text_value: str) -> str:
    """Repara mojibake tipo Latin-1 (Ã³ → ó)."""
    try:
        return text_value.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text_value


def needs_fix(value: str | None) -> bool:
    """Devuelve True si el valor parece corrupto."""
    if not value:
        return False
    return bool(BOX_DRAWING_RE.search(value) or LATIN1_MOJIBAKE_RE.search(value))


def try_fix(value: str) -> str:
    """Intenta reparar el valor con la estrategia correcta."""
    if BOX_DRAWING_RE.search(value):
        fixed = fix_cp437(value)
        if fixed != value:
            return fixed
    if LATIN1_MOJIBAKE_RE.search(value):
        fixed = fix_latin1(value)
        if fixed != value:
            return fixed
    return value


# Columnas de texto a revisar por tabla
COLUMNS_BY_TABLE = {
    "customer": [
        "name", "address", "city", "state", "province_code",
        "municipality_code", "country", "phone", "notes",
        "assigned_salesperson", "category", "gender",
    ],
    "supplier": [
        "name", "business_name", "address", "city", "province",
        "country", "phone", "notes", "contact_person", "category",
    ],
    "product": ["name", "description"],
}


def repair_table(db, table: str, columns: list[str], dry_run: bool = True) -> int:
    count = 0
    rows = db.execute(text(f"SELECT id, {', '.join(columns)} FROM {table}")).fetchall()

    for row in rows:
        row_id = row[0]
        updates: dict[str, str] = {}

        for i, col in enumerate(columns):
            val = row[i + 1]
            if val and needs_fix(val):
                fixed = try_fix(val)
                if fixed != val:
                    updates[col] = fixed

        if updates:
            count += 1
            sample_col = list(updates.keys())[0]
            old_val = row[columns.index(sample_col) + 1]
            new_val = updates[sample_col]
            print(f"  [{table} id={row_id}] {sample_col}: {repr(old_val)} → {repr(new_val)}")
            if not dry_run:
                set_clause = ", ".join(f"{c} = :{c}" for c in updates)
                params = {**updates, "row_id": row_id}
                db.execute(text(f"UPDATE {table} SET {set_clause} WHERE id = :row_id"), params)

    return count


def main(apply: bool = False) -> None:
    dry_run = not apply
    if dry_run:
        print("=== MODO SIMULACIÓN (dry-run) — no se modificará nada ===")
        print("=== Usar --apply para aplicar los cambios ===\n")
    else:
        print("=== APLICANDO CAMBIOS ===\n")

    db = SessionLocal()
    total = 0
    try:
        for table, columns in COLUMNS_BY_TABLE.items():
            try:
                count = repair_table(db, table, columns, dry_run=dry_run)
                print(f"✓ {table}: {count} registro(s) con mojibake encontrado(s)")
                total += count
            except Exception as e:
                print(f"✗ {table}: error — {e}")

        print(f"\nTotal: {total} registro(s) afectado(s)")

        if not dry_run and total > 0:
            db.commit()
            print("✅ Cambios guardados en la base de datos")
        elif dry_run and total > 0:
            print("\nEjecutar con --apply para aplicar los cambios")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    main(apply=apply)
