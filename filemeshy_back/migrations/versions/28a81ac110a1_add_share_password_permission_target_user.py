"""add password, permission and directed recipient to shares (Ronda 3: compartir granular)

Revision ID: 28a81ac110a1
Revises: a434107d6eac
Create Date: 2026-09-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '28a81ac110a1'
down_revision = 'a434107d6eac'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('shares', sa.Column('password_hash', sa.String(length=255), nullable=True))
    op.add_column(
        'shares',
        sa.Column('permission', sa.String(length=10), nullable=False, server_default='view'),
    )
    op.add_column(
        'shares',
        sa.Column('shared_with_user_id', postgresql.UUID(as_uuid=True), nullable=True),
    )

    # `token` deja de ser obligatorio -- un share dirigido a un usuario
    # específico (shared_with_user_id) no necesita link público.
    op.alter_column('shares', 'token', existing_type=sa.String(length=64), nullable=True)

    op.create_foreign_key(
        'shares_shared_with_user_id_fkey',
        'shares', 'users',
        ['shared_with_user_id'], ['id'],
        ondelete='CASCADE',
    )
    op.create_index('ix_share_shared_with_user_id', 'shares', ['shared_with_user_id'], unique=False)

    # Un share siempre tiene que ser accesible por AL MENOS una vía -- nunca
    # token Y shared_with_user_id NULL a la vez (el `ck_share_exactly_one_target`
    # existente, sobre file_id/folder_id, no se toca).
    op.create_check_constraint(
        'ck_share_token_or_recipient',
        'shares',
        '(token IS NOT NULL) OR (shared_with_user_id IS NOT NULL)',
    )


def downgrade() -> None:
    op.drop_constraint('ck_share_token_or_recipient', 'shares', type_='check')
    op.drop_index('ix_share_shared_with_user_id', table_name='shares')
    op.drop_constraint('shares_shared_with_user_id_fkey', 'shares', type_='foreignkey')
    # NOTA: si existen filas de shares dirigidos (token NULL) al momento de
    # bajar esta migración, este alter falla (violaría NOT NULL) -- downgrade
    # asume que no hay datos de Ronda 3 en producción todavía, mismo criterio
    # que el resto de las migraciones de este proyecto (no son reversibles
    # con datos reales de la feature que agregan).
    op.alter_column('shares', 'token', existing_type=sa.String(length=64), nullable=False)
    op.drop_column('shares', 'shared_with_user_id')
    op.drop_column('shares', 'permission')
    op.drop_column('shares', 'password_hash')
