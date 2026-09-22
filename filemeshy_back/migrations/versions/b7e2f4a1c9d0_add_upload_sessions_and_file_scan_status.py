"""add upload_sessions and files.scan_status (Ronda 9: coordinación de
subida multipart, sesiones de upload, cuota)

Revision ID: b7e2f4a1c9d0
Revises: d4e8a1f2b9c6
Create Date: 2026-09-22 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'b7e2f4a1c9d0'
down_revision = 'd4e8a1f2b9c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── files.scan_status ───────────────────────────────────────────────
    # 'clean' | 'pending' | 'infected'. `server_default='clean'` hace DOS
    # cosas en un solo statement: (1) backfillea TODAS las filas EXISTENTES
    # a 'clean' -- ya pasaron el escaneo síncrono de ClamAV que exige
    # `_scan_for_malware_or_raise` en app/files/router.py antes de que
    # existieran (Ronda 7), así que es la verdad; (2) hace que cualquier
    # fila NUEVA creada por el camino de upload SÍNCRONO existente
    # (≤MAX_UPLOAD_SIZE_MB, sin cambios en esta ronda) nazca 'clean'
    # automáticamente, sin que ese código (app/files/router.py,
    # app/files/service.py -- fuera de alcance de este agente en esta
    # ronda) tenga que cambiar una sola línea. Solo el camino NUEVO de
    # subida multipart (`app/uploads/service.py::complete_upload`) setea
    # 'pending' explícitamente.
    op.add_column(
        'files',
        sa.Column('scan_status', sa.String(length=20), nullable=False, server_default='clean'),
    )
    # 'scan_failed' -- agregado durante esta misma ronda: el agente de
    # AV/infra (app/worker/tasks/av_scan.py) lo usa para reintentos
    # agotados (clamd sigue sin responder tras los reintentos configurados)
    # -- estado distinto de 'infected' (amenaza real confirmada) y de
    # 'pending' (todavía no se intentó escanear). Un archivo 'scan_failed'
    # queda invisible igual que 'pending'/'infected' (el filtro central de
    # `app/files/repository.py::CRUDFile` solo deja pasar 'clean').
    op.create_check_constraint(
        'ck_file_scan_status',
        'files',
        "scan_status IN ('clean', 'pending', 'infected', 'scan_failed')",
    )

    # ── upload_sessions ──────────────────────────────────────────────────
    op.create_table(
        'upload_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('declared_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('mime_type_declared', sa.String(length=255), nullable=False),
        sa.Column('target_folder_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('storage_key', sa.String(length=500), nullable=False),
        sa.Column('minio_upload_id', sa.String(length=500), nullable=False),
        sa.Column('part_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('part_count', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='in_progress'),
        sa.Column('quota_reserved_bytes', sa.BigInteger(), nullable=False),
        sa.Column('file_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_folder_id'], ['folders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed_pending_scan', 'aborted', 'failed')",
            name='ck_upload_session_status',
        ),
    )
    op.create_index('ix_upload_session_owner_id', 'upload_sessions', ['owner_id'], unique=False)
    # Compuesto -- es exactamente el WHERE de la tarea periódica de limpieza
    # (status='in_progress' AND expires_at < now(), ver
    # app/worker/tasks/uploads.py::cleanup_abandoned_upload_sessions).
    op.create_index(
        'ix_upload_session_status_expires', 'upload_sessions', ['status', 'expires_at'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_upload_session_status_expires', table_name='upload_sessions')
    op.drop_index('ix_upload_session_owner_id', table_name='upload_sessions')
    op.drop_table('upload_sessions')

    op.drop_constraint('ck_file_scan_status', 'files', type_='check')
    op.drop_column('files', 'scan_status')
