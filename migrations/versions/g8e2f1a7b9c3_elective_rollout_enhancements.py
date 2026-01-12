"""Add elective rollout enhancements (deadline, templates, pool, audit)

Revision ID: g8e2f1a7b9c3
Revises: a1b2c3d4e5f6
Create Date: 2025-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g8e2f1a7b9c3'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to elective_window table
    op.add_column('elective_window', sa.Column('deadline_at', sa.DateTime(), nullable=True))
    op.add_column('elective_window', sa.Column('reminder_sent_at', sa.DateTime(), nullable=True))
    op.add_column('elective_window', sa.Column('rollout_batch_id', sa.String(36), nullable=True))
    
    # Create index for batch_id for faster grouping
    op.create_index('ix_elective_window_rollout_batch_id', 'elective_window', ['rollout_batch_id'], unique=False)
    
    # Create elective_rollout_template table
    op.create_table('elective_rollout_template',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('dept_id', sa.Integer(), nullable=True),
        sa.Column('class_level', sa.String(2), nullable=False),
        sa.Column('target_semester_no', sa.Integer(), nullable=False),
        sa.Column('buckets_config', sa.Text(), nullable=True),
        sa.Column('min_batch_size', sa.Integer(), nullable=True, default=12),
        sa.Column('default_duration_days', sa.Integer(), nullable=True, default=7),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('created_by_id', sa.String(36), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['dept_id'], ['department.dept_id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['staff_profile.staff_id'])
    )
    
    # Create elective_subject_pool table (for rollout independent of course structure)
    op.create_table('elective_subject_pool',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('target_class_level', sa.String(2), nullable=False),
        sa.Column('target_semester_no', sa.Integer(), nullable=False),
        sa.Column('bucket', sa.String(50), nullable=False),
        sa.Column('academic_year', sa.String(20), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('created_by_id', sa.String(36), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['subject_id'], ['subject.subject_id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['staff_profile.staff_id']),
        sa.UniqueConstraint('subject_id', 'target_class_level', 'target_semester_no', 'bucket', 'academic_year',
                           name='uq_elective_pool_subject')
    )
    
    # Create elective_audit_log table (for tracking and recovery)
    op.create_table('elective_audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.String(50), nullable=False),
        sa.Column('window_id', sa.Integer(), nullable=True),
        sa.Column('student_id', sa.String(36), nullable=True),
        sa.Column('subject_id', sa.Integer(), nullable=True),
        sa.Column('old_value', sa.JSON(), nullable=True),
        sa.Column('new_value', sa.JSON(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('performed_by_id', sa.String(36), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['window_id'], ['elective_window.id']),
        sa.ForeignKeyConstraint(['student_id'], ['student_profile.student_id']),
        sa.ForeignKeyConstraint(['subject_id'], ['subject.subject_id']),
        sa.ForeignKeyConstraint(['performed_by_id'], ['user_master.user_id'])
    )
    
    # Create index for audit log queries
    op.create_index('ix_elective_audit_log_action_type', 'elective_audit_log', ['action_type'], unique=False)
    op.create_index('ix_elective_audit_log_timestamp', 'elective_audit_log', ['timestamp'], unique=False)


def downgrade():
    # Drop audit log indexes and table
    op.drop_index('ix_elective_audit_log_timestamp', table_name='elective_audit_log')
    op.drop_index('ix_elective_audit_log_action_type', table_name='elective_audit_log')
    op.drop_table('elective_audit_log')
    
    # Drop subject pool table
    op.drop_table('elective_subject_pool')
    
    # Drop template table
    op.drop_table('elective_rollout_template')
    
    # Drop index
    op.drop_index('ix_elective_window_rollout_batch_id', table_name='elective_window')
    
    # Remove columns from elective_window
    op.drop_column('elective_window', 'rollout_batch_id')
    op.drop_column('elective_window', 'reminder_sent_at')
    op.drop_column('elective_window', 'deadline_at')
