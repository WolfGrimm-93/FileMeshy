"""add is_favorite to files and folders

Revision ID: a3f7c9d21b4e
Revises: f1422639dbca
Create Date: 2026-09-19 18:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3f7c9d21b4e'
down_revision = 'f1422639dbca'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'files',
        sa.Column('is_favorite', sa.Boolean(), server_default='false', nullable=False),
    )
    op.add_column(
        'folders',
        sa.Column('is_favorite', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('folders', 'is_favorite')
    op.drop_column('files', 'is_favorite')
