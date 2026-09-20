"""add file_versions (Ronda 4: versionado de archivos)

Revision ID: c1d9e5f3a7b2
Revises: 28a81ac110a1
Create Date: 2026-09-20 12:30:00.000000

"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import column, table
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'c1d9e5f3a7b2'
down_revision = '28a81ac110a1'
branch_labels = None
depends_on = None


def _uuid7() -> uuid.UUID:
    """Mismo mecanismo que `app.shared.utils.uuid7.uuid7()` (norma del
    proyecto: todo id nuevo es UUID v7) -- reimplementado acá en vez de
    importar el módulo de la app porque las migraciones de este proyecto no
    importan código de `app/` (son infraestructura de Alembic aislada, ver
    el resto de este directorio), pero la librería de bajo nivel
    (`uuid_utils`, ya una dependencia real del proyecto) es la misma."""
    import uuid_utils

    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)


def _backfill_pre_existing_files_as_version_1(connection) -> int:
    """Da de alta la `FileVersion` 1 de todo `File` ACTIVO que todavía no
    tiene NINGUNA versión (sin backfill, esos archivos quedarían con CERO
    filas en `file_versions` -- rompe la invariante "un archivo SIEMPRE
    tiene al menos una versión" que documenta `app/files/models.py::FileVersion`,
    y es más grave que un simple dato faltante: si alguien sube una versión
    nueva sobre uno de esos archivos "viejos", `get_max_version_number` da 0
    y la próxima queda numerada como "versión 1" -- el contenido ORIGINAL
    que había antes de esa subida se pierde para siempre sin aviso, el
    `storage_key` viejo queda huérfano en MinIO y nadie se entera. Hallazgo
    real de la revisión adversarial de Ronda 4, 2026-09-20).

    IDEMPOTENTE a propósito (`NOT EXISTS` contra `file_versions`, no "traer
    todos los archivos activos a ciegas"): un archivo que YA tiene una
    versión (subido normalmente después de que esta migración corrió una
    vez, o backfillado en una corrida anterior) se salta en vez de
    reintentar insertarle otra versión 1 y chocar con
    `uq_file_version_number`. Confirmado en vivo con el test de regresión
    de esta misma función (`tests/test_migration_backfill_versions.py`):
    sin este filtro, invocarla una segunda vez sobre una DB que ya corrió
    `alembic upgrade head` una vez revienta con `UniqueViolation`.

    Archivos ya en la papelera (`deleted_at IS NOT NULL`) se excluyen a
    propósito -- no importan para versionado futuro (si se restauran de la
    papelera después de esta migración, quedan sin historial, pero un
    archivo restaurado de la papelera no es un caso que esta ronda haya
    prometido cubrir; documentado como limitación conocida, no bloqueante).

    `created_by_id` = `owner_id` del archivo -- no hay forma de saber quién
    subió el contenido ORIGINAL antes de que existiera este concepto
    (`created_by_id` en `file_versions`), el dueño es la mejor aproximación
    disponible (mismo criterio que usa `upload_file` para la versión 1 de
    un archivo nuevo, donde quien sube y quien es dueño son la misma
    persona en el caso común). `created_at` de la versión = `created_at`
    del archivo (la fecha real del upload original), no `now()` -- más
    preciso para el historial que mostrarle al usuario."""
    files_table = table(
        'files',
        column('id', postgresql.UUID(as_uuid=True)),
        column('storage_key', sa.String),
        column('size_bytes', sa.BigInteger),
        column('mime_type', sa.String),
        column('owner_id', postgresql.UUID(as_uuid=True)),
        column('created_at', sa.DateTime(timezone=True)),
        column('deleted_at', sa.DateTime(timezone=True)),
    )
    file_versions_table = table(
        'file_versions',
        column('id', postgresql.UUID(as_uuid=True)),
        column('file_id', postgresql.UUID(as_uuid=True)),
        column('version_number', sa.Integer),
        column('storage_key', sa.String),
        column('size_bytes', sa.BigInteger),
        column('mime_type', sa.String),
        column('created_by_id', postgresql.UUID(as_uuid=True)),
        column('created_at', sa.DateTime(timezone=True)),
    )

    # `NOT EXISTS ... file_versions` -- además de excluir los ya borrados,
    # esto hace la función IDEMPOTENTE: solo backfillea archivos que
    # todavía no tienen NINGUNA versión. Necesario porque un archivo puede
    # ya tener su versión 1 real (subido normalmente después de que esta
    # migración corrió una vez) -- sin este filtro, volver a invocar la
    # función (ej. un test de regresión, o un reintento manual) choca con
    # `uq_file_version_number` en vez de no hacer nada sobre lo que ya está
    # bien. Confirmado en vivo: sin el filtro, el test de regresión de esta
    # misma función fallaba con `UniqueViolation` al insertar sobre archivos
    # que la corrida real de `alembic upgrade head` ya había backfillado.
    existing_files = connection.execute(
        sa.select(
            files_table.c.id,
            files_table.c.storage_key,
            files_table.c.size_bytes,
            files_table.c.mime_type,
            files_table.c.owner_id,
            files_table.c.created_at,
        ).where(
            files_table.c.deleted_at.is_(None),
            ~sa.exists().where(file_versions_table.c.file_id == files_table.c.id),
        )
    ).fetchall()

    if not existing_files:
        return 0

    rows = [
        {
            'id': _uuid7(),
            'file_id': f.id,
            'version_number': 1,
            'storage_key': f.storage_key,
            'size_bytes': f.size_bytes,
            'mime_type': f.mime_type,
            'created_by_id': f.owner_id,
            'created_at': f.created_at,
        }
        for f in existing_files
    ]
    connection.execute(sa.insert(file_versions_table), rows)
    return len(rows)


def upgrade() -> None:
    op.create_table(
        'file_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('file_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('storage_key', sa.String(length=500), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('mime_type', sa.String(length=255), nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('file_id', 'version_number', name='uq_file_version_number'),
    )
    op.create_index('ix_file_version_file_id', 'file_versions', ['file_id'], unique=False)

    # Backfill OBLIGATORIO, no opcional -- ver docstring de
    # `_backfill_pre_existing_files_as_version_1` para el motivo (pérdida de
    # datos silenciosa sin esto).
    _backfill_pre_existing_files_as_version_1(op.get_bind())


def downgrade() -> None:
    op.drop_index('ix_file_version_file_id', table_name='file_versions')
    op.drop_table('file_versions')
