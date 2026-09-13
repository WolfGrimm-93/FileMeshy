"""Helpers compartidos para la migracion de PK integer -> UUID v7.

Extraidos del patron que Tier 0 repitio identico en sus 10 pares de
migraciones (confirmado por diff: los bodies de upgrade()/downgrade() eran
byte-a-byte iguales salvo la lista TABLES). Tier 1 en adelante ademas
necesita actualizar columnas FK que apuntan a las tablas migradas -- ese
patron no existia en Tier 0 (evito a proposito las tablas con FKs
entrantes), se agrega aca por primera vez.

Uso tipico (migracion A del padre, agregar+backfill):
    add_and_backfill_id_v7(op, op.get_bind(), ['parent_table'])

Migracion B del padre (swap de PK) -- si alguna tabla hija tiene una FK
que depende del pkey viejo, hay que dropearla ACA (no se puede dropear el
pkey con una FK todavia colgando de el). dependent_fks es la lista de
constraints de tablas hijas que dependen de este pkey; se dropean antes de
tocar el pkey y NO se recrean aca -- eso lo hace swap_fk() de la tabla hija,
en una migracion posterior, contra el `id` nuevo (UUID):
    swap_pk(op, ['parent_table'], dependent_fks=[
        {"table": "child_table", "constraint": "child_table_parent_id_fkey"},
    ])

Migraciones de la tabla hija (despues de que el padre ya tiene id en UUID):
    add_and_backfill_fk_v7(op, op.get_bind(), 'child_table', 'parent_id', 'parent_table', nullable=False)
    ... (migracion B) ...
    swap_fk(op, 'child_table', 'parent_id', 'parent_table',
            constraint_name='child_table_parent_id_fkey', nullable=False,
            index_name='ix_child_table_parent_id')
"""
import uuid

import sqlalchemy as sa
import uuid_utils
from sqlalchemy.dialects import postgresql

BATCH = 5000


def _new_uuid7() -> uuid.UUID:
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)


# ─── Patron de PK (igual a Tier 0, mas el manejo de FKs entrantes) ────────

def add_and_backfill_id_v7(op, conn, tables, concurrent=()):
    """Migracion A: agrega id_v7, backfillea en lotes, indice unico."""
    for t in tables:
        op.add_column(t, sa.Column('id_v7', postgresql.UUID(as_uuid=True), nullable=True))
        while True:
            rows = conn.execute(
                sa.text(f"SELECT id FROM {t} WHERE id_v7 IS NULL ORDER BY id LIMIT :n"),
                {"n": BATCH},
            ).fetchall()
            if not rows:
                break
            conn.execute(
                sa.text(f"UPDATE {t} SET id_v7 = :new_id WHERE id = :old_id"),
                [{"old_id": r.id, "new_id": _new_uuid7()} for r in rows],
            )
        op.execute(f"ALTER TABLE {t} ADD CONSTRAINT ck_{t}_id_v7_not_null CHECK (id_v7 IS NOT NULL) NOT VALID")
        op.execute(f"ALTER TABLE {t} VALIDATE CONSTRAINT ck_{t}_id_v7_not_null")
        if t in concurrent:
            with op.get_context().autocommit_block():
                op.execute(f"CREATE UNIQUE INDEX CONCURRENTLY ix_{t}_id_v7 ON {t} (id_v7)")
        else:
            op.create_index(f"ix_{t}_id_v7", t, ['id_v7'], unique=True)


def drop_id_v7(op, tables):
    """Downgrade de add_and_backfill_id_v7."""
    for t in reversed(tables):
        op.drop_index(f"ix_{t}_id_v7", table_name=t)
        op.drop_constraint(f"ck_{t}_id_v7_not_null", t, type_='check')
        op.drop_column(t, 'id_v7')


def swap_pk(op, tables, concurrent=(), dependent_fks=()):
    """Migracion B: id -> legacy_id, id_v7 -> id (PK).

    dependent_fks: constraints de tablas hijas que referencian el pkey viejo
    -- hay que dropearlas antes de poder dropear {t}_pkey (Postgres no deja
    dropear un indice/pkey con una FK todavia colgando de el). No se
    recrean aca: la migracion de la tabla hija (swap_fk) las crea de nuevo
    contra el `id` ya en UUID.

    Ademas crea un indice unico sobre legacy_id (los valores ya eran unicos
    -- era la PK vieja --, solo falta la restriccion explicita). Lo necesita
    cualquier FK de downgrade que deba referenciar legacy_id (ver
    unswap_fk)."""
    for fk in dependent_fks:
        op.execute(f"ALTER TABLE {fk['table']} DROP CONSTRAINT {fk['constraint']}")
    for t in tables:
        op.execute(f"ALTER TABLE {t} DROP CONSTRAINT {t}_pkey")
        op.alter_column(t, 'id', new_column_name='legacy_id')
        op.alter_column(t, 'id_v7', new_column_name='id')
        op.execute(f"ALTER TABLE {t} ADD CONSTRAINT {t}_pkey PRIMARY KEY USING INDEX ix_{t}_id_v7")
        op.execute(f"ALTER TABLE {t} DROP CONSTRAINT ck_{t}_id_v7_not_null")
        op.create_index(f"ix_{t}_legacy_id", t, ['legacy_id'], unique=True)


def unswap_pk(op, tables, concurrent=(), dependent_fks=()):
    """Downgrade de swap_pk -- deja la tabla como quedo la migracion A.

    En este punto de la secuencia de downgrade (reversa), las FKs de
    dependent_fks ya fueron recreadas por unswap_fk() de la tabla hija,
    apuntando a legacy_id -- hay que dropearlas para poder dropear
    ix_{t}_legacy_id, y recrearlas al final apuntando al `id` ya renombrado
    (entero de nuevo), restaurando el estado original pre-migracion."""
    for fk in dependent_fks:
        op.execute(f"ALTER TABLE {fk['table']} DROP CONSTRAINT {fk['constraint']}")
    for t in reversed(tables):
        op.drop_index(f"ix_{t}_legacy_id", table_name=t)
        op.execute(f"ALTER TABLE {t} DROP CONSTRAINT {t}_pkey")
        op.alter_column(t, 'id', new_column_name='id_v7')
        op.alter_column(t, 'legacy_id', new_column_name='id')
        op.execute(f"ALTER TABLE {t} ADD PRIMARY KEY (id)")
        op.execute(f"ALTER TABLE {t} ADD CONSTRAINT ck_{t}_id_v7_not_null CHECK (id_v7 IS NOT NULL) NOT VALID")
        op.execute(f"ALTER TABLE {t} VALIDATE CONSTRAINT ck_{t}_id_v7_not_null")
        if t in concurrent:
            with op.get_context().autocommit_block():
                op.execute(f"CREATE UNIQUE INDEX CONCURRENTLY ix_{t}_id_v7 ON {t} (id_v7)")
        else:
            op.create_index(f"ix_{t}_id_v7", t, ['id_v7'], unique=True)
    for fk in dependent_fks:
        fk_clause = (
            f"ALTER TABLE {fk['table']} ADD CONSTRAINT {fk['constraint']} "
            f"FOREIGN KEY ({fk['column']}) REFERENCES {fk['parent']}(id)"
        )
        if fk.get('ondelete'):
            fk_clause += f" ON DELETE {fk['ondelete']}"
        op.execute(fk_clause)


# ─── Patron nuevo: columna FK que apunta a una tabla ya migrada ───────────
# Requiere que `parent_table` ya haya pasado por swap_pk (su `id` es UUID,
# su `legacy_id` conserva los enteros originales) antes de correr esto.

def add_and_backfill_fk_v7(op, conn, child_table, fk_column, parent_table, nullable=True):
    """Migracion A del lado FK: agrega {fk_column}_v7, backfillea via join
    contra legacy_id del padre (que todavia tiene los enteros originales)."""
    op.add_column(child_table, sa.Column(f"{fk_column}_v7", postgresql.UUID(as_uuid=True), nullable=True))
    conn.execute(sa.text(
        f"UPDATE {child_table} c SET {fk_column}_v7 = p.id "
        f"FROM {parent_table} p WHERE c.{fk_column} = p.legacy_id"
    ))
    if not nullable:
        op.execute(
            f"ALTER TABLE {child_table} ADD CONSTRAINT ck_{child_table}_{fk_column}_v7_not_null "
            f"CHECK ({fk_column}_v7 IS NOT NULL) NOT VALID"
        )
        op.execute(f"ALTER TABLE {child_table} VALIDATE CONSTRAINT ck_{child_table}_{fk_column}_v7_not_null")


def drop_fk_v7(op, child_table, fk_column, nullable=True):
    """Downgrade de add_and_backfill_fk_v7."""
    if not nullable:
        op.drop_constraint(f"ck_{child_table}_{fk_column}_v7_not_null", child_table, type_='check')
    op.drop_column(child_table, f"{fk_column}_v7")


def swap_fk(op, child_table, fk_column, parent_table, constraint_name, nullable=True, ondelete=None, index_name=None):
    """Migracion B del lado FK: renombra {fk_column} -> {fk_column}_legacy y
    {fk_column}_v7 -> {fk_column}, crea la FK nueva contra parent_table(id)
    (ya UUID). La FK vieja NO se dropea aca -- ya la dropeo swap_pk() del
    padre (no se puede dropear su pkey con esta FK todavia dependiendo de el).

    Nota importante: si {fk_column} participa de un indice compuesto (ej.
    UNIQUE(device_id, company_settings_id)), ese indice sigue el rename por
    attnum -- pero seguira apuntando al valor legacy (integer), no al nuevo
    UUID, porque Postgres asocia los indices a la columna fisica, no al
    nombre. Hay que dropear y recrear esos indices compuestos aparte, en la
    migracion de la tabla especifica (no lo hace este helper de forma
    generica).
    """
    if index_name:
        op.drop_index(index_name, table_name=child_table)
    op.alter_column(child_table, fk_column, new_column_name=f"{fk_column}_legacy")
    if not nullable:
        # La columna vieja hereda el NOT NULL del rename -- pero la app deja
        # de escribirla desde aca (solo queda como rastro historico), asi
        # que un INSERT nuevo rompe con NotNullViolation si no se afloja.
        # Bug real encontrado en Tier 2 (sessions.user_id_legacy) al hacer
        # login -- el INSERT de una sesion nueva fallaba.
        op.alter_column(child_table, f"{fk_column}_legacy", nullable=True)
    op.alter_column(child_table, f"{fk_column}_v7", new_column_name=fk_column)
    fk_clause = f"ALTER TABLE {child_table} ADD CONSTRAINT {constraint_name} FOREIGN KEY ({fk_column}) REFERENCES {parent_table}(id)"
    if ondelete:
        fk_clause += f" ON DELETE {ondelete}"
    op.execute(fk_clause)
    if not nullable:
        # Promover el CHECK ... NOT VALID/VALIDATE (que solo valida datos, no
        # es un NOT NULL real de columna) a un NOT NULL real antes de
        # dropearlo -- si no, la columna queda nullable de facto.
        op.alter_column(child_table, fk_column, nullable=False)
        op.execute(f"ALTER TABLE {child_table} DROP CONSTRAINT ck_{child_table}_{fk_column}_v7_not_null")
    if index_name:
        op.create_index(index_name, child_table, [fk_column])


def unswap_fk(op, child_table, fk_column, parent_table, constraint_name, nullable=True, ondelete=None, index_name=None):
    """Downgrade de swap_fk. Dropea la FK 'nueva' (contra parent.id UUID,
    creada por swap_fk), renombra las columnas de vuelta, y recrea la FK
    apuntando a parent.legacy_id (temporal -- unswap_pk() del padre la
    dropea y recrea de nuevo mas adelante, contra el `id` entero final)."""
    if index_name:
        op.drop_index(index_name, table_name=child_table)
    op.execute(f"ALTER TABLE {child_table} DROP CONSTRAINT {constraint_name}")
    op.alter_column(child_table, fk_column, new_column_name=f"{fk_column}_v7")
    op.alter_column(child_table, f"{fk_column}_legacy", new_column_name=fk_column)
    if not nullable:
        # Restaurar el NOT NULL real que swap_fk aflojo en legacy -- volver
        # exactamente al estado pre-migracion.
        op.alter_column(child_table, fk_column, nullable=False)
        # Volver al estado exacto de la migracion A: NOT NULL via CHECK, no
        # como atributo real de columna (swap_fk lo promueve a real al subir).
        op.alter_column(child_table, f"{fk_column}_v7", nullable=True)
        op.execute(
            f"ALTER TABLE {child_table} ADD CONSTRAINT ck_{child_table}_{fk_column}_v7_not_null "
            f"CHECK ({fk_column}_v7 IS NOT NULL) NOT VALID"
        )
        op.execute(f"ALTER TABLE {child_table} VALIDATE CONSTRAINT ck_{child_table}_{fk_column}_v7_not_null")
    old_fk_clause = f"ALTER TABLE {child_table} ADD CONSTRAINT {constraint_name} FOREIGN KEY ({fk_column}) REFERENCES {parent_table}(legacy_id)"
    if ondelete:
        old_fk_clause += f" ON DELETE {ondelete}"
    op.execute(old_fk_clause)
    if index_name:
        op.create_index(index_name, child_table, [fk_column])
