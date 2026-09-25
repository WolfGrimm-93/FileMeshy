"""add attempted_at a file_content_index (barrido de pending huerfanos)

Revision ID: f2b8d4e6a1c3
Revises: e5a1c7d3b9f2
Create Date: 2026-09-25 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2b8d4e6a1c3'
down_revision = 'e5a1c7d3b9f2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'file_content_index',
        sa.Column('attempted_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('file_content_index', 'attempted_at')
