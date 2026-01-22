"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create calls table
    op.create_table(
        'calls',
        sa.Column('call_id', sa.Text(), nullable=False),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('ended_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('language', sa.Text(), nullable=True),
        sa.Column('from_number', sa.Text(), nullable=True),
        sa.Column('to_number', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), server_default='active', nullable=True),
        sa.PrimaryKeyConstraint('call_id')
    )

    # Create turns table
    op.create_table(
        'turns',
        sa.Column('call_id', sa.Text(), nullable=False),
        sa.Column('turn_id', sa.Integer(), nullable=False),
        sa.Column('user_text', sa.Text(), nullable=True),
        sa.Column('intent', sa.Text(), nullable=True),
        sa.Column('tool_calls', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('assistant_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.call_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('call_id', 'turn_id')
    )

    # Create audio_files table
    op.create_table(
        'audio_files',
        sa.Column('call_id', sa.Text(), nullable=False),
        sa.Column('turn_id', sa.Integer(), nullable=False),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.CheckConstraint("kind IN ('input', 'output')", name='audio_files_kind_check'),
        sa.ForeignKeyConstraint(['call_id', 'turn_id'], ['turns.call_id', 'turns.turn_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('call_id', 'turn_id', 'kind')
    )

    # Create recordings table
    op.create_table(
        'recordings',
        sa.Column('call_id', sa.Text(), nullable=False),
        sa.Column('recording_sid', sa.Text(), nullable=False),
        sa.Column('recording_url', sa.Text(), nullable=False),
        sa.Column('from_number', sa.Text(), nullable=True),
        sa.Column('to_number', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.call_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('call_id')
    )

    # Create reservations table (from CRM)
    op.create_table(
        'reservations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('reservation_datetime', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('people', sa.Integer(), nullable=False),
        sa.Column('phone', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), server_default='active', nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create customer_preferences table (from CRM)
    op.create_table(
        'customer_preferences',
        sa.Column('customer_key', sa.Text(), nullable=False),
        sa.Column('preferences', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('customer_key')
    )


def downgrade() -> None:
    op.drop_table('customer_preferences')
    op.drop_table('reservations')
    op.drop_table('recordings')
    op.drop_table('audio_files')
    op.drop_table('turns')
    op.drop_table('calls')
