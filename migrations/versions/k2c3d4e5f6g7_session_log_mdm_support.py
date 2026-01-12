"""Add MDM/OE support to session_log table

Revision ID: k2c3d4e5f6g7
Revises: j1b2c3d4e5f6
Create Date: 2026-01-10 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'k2c3d4e5f6g7'
down_revision = 'j1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Make schedule_id nullable (for MDM sessions that don't have a WeeklySchedule)
    with op.batch_alter_table('session_log', schema=None) as batch_op:
        batch_op.alter_column('schedule_id', nullable=True)
        batch_op.add_column(sa.Column('extra_session_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('subject_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('section_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_session_extra', 'extra_session', ['extra_session_id'], ['id'])
        batch_op.create_foreign_key('fk_session_subject', 'subject', ['subject_id'], ['subject_id'])
        batch_op.create_foreign_key('fk_session_section', 'class_section', ['section_id'], ['section_id'])
    
    # 2. Create indexes for efficient queries
    op.create_index('ix_session_log_extra_session_id', 'session_log', ['extra_session_id'], unique=False)
    op.create_index('ix_session_log_subject_id', 'session_log', ['subject_id'], unique=False)
    op.create_index('ix_session_log_section_id', 'session_log', ['section_id'], unique=False)


def downgrade():
    # Drop indexes
    op.drop_index('ix_session_log_section_id', table_name='session_log')
    op.drop_index('ix_session_log_subject_id', table_name='session_log')
    op.drop_index('ix_session_log_extra_session_id', table_name='session_log')
    
    # Drop columns
    with op.batch_alter_table('session_log', schema=None) as batch_op:
        batch_op.drop_constraint('fk_session_section', type_='foreignkey')
        batch_op.drop_constraint('fk_session_subject', type_='foreignkey')
        batch_op.drop_constraint('fk_session_extra', type_='foreignkey')
        batch_op.drop_column('section_id')
        batch_op.drop_column('subject_id')
        batch_op.drop_column('extra_session_id')
        batch_op.alter_column('schedule_id', nullable=False)
