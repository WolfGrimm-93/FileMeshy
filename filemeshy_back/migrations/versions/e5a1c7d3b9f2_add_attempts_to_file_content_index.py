"""add attempts a file_content_index (tope de redelivery de la indexacion)

Revision ID: e5a1c7d3b9f2
Revises: b7e2f4a1c9d0
Create Date: 2026-09-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5a1c7d3b9f2'
down_revision = 'b7e2f4a1c9d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'file_content_index',
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('file_content_index', 'attempts')
