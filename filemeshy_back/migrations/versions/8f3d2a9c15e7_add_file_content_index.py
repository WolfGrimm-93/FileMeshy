"""add file_content_index (Ronda 6: búsqueda por contenido + OCR)

Revision ID: 8f3d2a9c15e7
Revises: c1d9e5f3a7b2
Create Date: 2026-09-20 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '8f3d2a9c15e7'
down_revision = 'c1d9e5f3a7b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'file_content_index',
        sa.Column('file_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content_text', sa.Text(), nullable=True),
        sa.Column('extraction_status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('indexed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('file_id'),
    )

    # `search_vector` es una columna GENERADA por Postgres (STORED), armada
    # con SQL crudo en vez de `sa.Column(..., sa.Computed(...))` -- el
    # soporte de SQLAlchemy para columnas generadas es más frágil de
    # modelar/migrar entre versiones que simplemente escribir el DDL real acá
    # (decisión de diseño de esta ronda, ver docstring de
    # `app.files.models.FileContentIndex`). `'spanish'` como configuración de
    # texto fija a propósito -- el resto del producto (nombres de archivo,
    # UI) ya está en español, no hace falta detección de idioma por
    # documento para esta primera versión de búsqueda por contenido.
    op.execute(
        """
        ALTER TABLE file_content_index
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('spanish', coalesce(content_text, ''))) STORED
        """
    )
    op.execute(
        """
        CREATE INDEX ix_file_content_index_search_vector
        ON file_content_index
        USING GIN (search_vector)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_file_content_index_search_vector")
    op.drop_table('file_content_index')
