"""add tags, file_tags and folder_tags

Revision ID: a434107d6eac
Revises: a3f7c9d21b4e
Create Date: 2026-09-20 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'a434107d6eac'
down_revision = 'a3f7c9d21b4e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tags',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('color', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_id', 'name', name='uq_tag_owner_name'),
    )
    op.create_index('ix_tags_owner_id', 'tags', ['owner_id'], unique=False)

    op.create_table(
        'file_tags',
        sa.Column('file_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tag_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('file_id', 'tag_id'),
    )
    op.create_index('ix_file_tags_tag_id', 'file_tags', ['tag_id'], unique=False)

    op.create_table(
        'folder_tags',
        sa.Column('folder_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tag_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['folder_id'], ['folders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('folder_id', 'tag_id'),
    )
    op.create_index('ix_folder_tags_tag_id', 'folder_tags', ['tag_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_folder_tags_tag_id', table_name='folder_tags')
    op.drop_table('folder_tags')
    op.drop_index('ix_file_tags_tag_id', table_name='file_tags')
    op.drop_table('file_tags')
    op.drop_index('ix_tags_owner_id', table_name='tags')
    op.drop_table('tags')
