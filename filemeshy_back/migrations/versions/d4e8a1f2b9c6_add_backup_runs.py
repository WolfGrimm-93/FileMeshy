"""add backup_runs (Ronda 7: backups automaticos + verificacion)

Revision ID: d4e8a1f2b9c6
Revises: 8f3d2a9c15e7
Create Date: 2026-09-21 07:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'd4e8a1f2b9c6'
down_revision = '8f3d2a9c15e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'backup_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('backup_type', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('storage_location', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_backup_runs_backup_type', 'backup_runs', ['backup_type'])
    op.create_index('ix_backup_runs_started_at', 'backup_runs', ['started_at'])


def downgrade() -> None:
    op.drop_index('ix_backup_runs_started_at', table_name='backup_runs')
    op.drop_index('ix_backup_runs_backup_type', table_name='backup_runs')
    op.drop_table('backup_runs')
