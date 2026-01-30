"""MDM/OE Revamp - Pool and Selection System

Revision ID: i0a1b2c3d4e5
Revises: h9f3g2b8c4d5
Create Date: 2026-01-09 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'i0a1b2c3d4e5'
down_revision = 'h9f3g2b8c4d5'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create mdm_offering_pool table
    op.create_table('mdm_offering_pool',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(30), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('type', sa.String(10), nullable=False),
        sa.Column('direction', sa.String(10), nullable=False),
        sa.Column('l_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('t_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('p_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('credits', sa.Integer(), nullable=True, server_default='3'),
        sa.Column('assigned_faculty_id', sa.String(36), nullable=True),
        sa.Column('host_school_name', sa.String(200), nullable=True),
        sa.Column('host_contact_email', sa.String(100), nullable=True),
        sa.Column('capacity', sa.Integer(), nullable=True),
        sa.Column('schedule_pattern', sa.String(100), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('academic_year', sa.String(20), nullable=False),
        sa.Column('target_class_levels', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.func.current_timestamp()),
        sa.Column('created_by_id', sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(['assigned_faculty_id'], ['staff_profile.staff_id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['staff_profile.staff_id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', 'academic_year', name='uq_mdm_pool_code_year')
    )
    op.create_index('ix_mdm_pool_direction', 'mdm_offering_pool', ['direction'])
    op.create_index('ix_mdm_pool_type', 'mdm_offering_pool', ['type'])
    op.create_index('ix_mdm_pool_academic_year', 'mdm_offering_pool', ['academic_year'])

    # 2. Create mdm_outbound_window table
    op.create_table('mdm_outbound_window',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=True),
        sa.Column('class_level', sa.String(10), nullable=True),
        sa.Column('dept_id', sa.Integer(), nullable=True),
        sa.Column('course_type', sa.String(10), nullable=False),
        sa.Column('academic_year', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=True, server_default='Open'),
        sa.Column('min_batch_size', sa.Integer(), nullable=True, server_default='15'),
        sa.Column('deadline_at', sa.DateTime(), nullable=True),
        sa.Column('extension_deadline_at', sa.DateTime(), nullable=True),
        sa.Column('reminder_sent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.func.current_timestamp()),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('rollout_batch_id', sa.String(36), nullable=True),
        sa.Column('created_by_id', sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(['section_id'], ['class_section.section_id']),
        sa.ForeignKeyConstraint(['dept_id'], ['department.dept_id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['staff_profile.staff_id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mdm_window_status', 'mdm_outbound_window', ['status'])
    op.create_index('ix_mdm_window_academic_year', 'mdm_outbound_window', ['academic_year'])

    # 3. Create mdm_window_offering table (links pool to windows)
    op.create_table('mdm_window_offering',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('window_id', sa.Integer(), nullable=False),
        sa.Column('pool_id', sa.Integer(), nullable=False),
        sa.Column('window_capacity', sa.Integer(), nullable=True),
        sa.Column('final_status', sa.String(20), nullable=True, server_default='Pending'),
        sa.ForeignKeyConstraint(['window_id'], ['mdm_outbound_window.id']),
        sa.ForeignKeyConstraint(['pool_id'], ['mdm_offering_pool.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('window_id', 'pool_id', name='uq_mdm_window_offering')
    )

    # 4. Create mdm_outbound_selection table (student selections)
    op.create_table('mdm_outbound_selection',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.String(36), nullable=False),
        sa.Column('window_id', sa.Integer(), nullable=False),
        sa.Column('pool_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=True, server_default='Selected'),
        sa.Column('selected_at', sa.DateTime(), nullable=True, server_default=sa.func.current_timestamp()),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('external_marks', sa.Float(), nullable=True),
        sa.Column('external_grade', sa.String(5), nullable=True),
        sa.Column('marks_imported_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['student_id'], ['student_profile.student_id']),
        sa.ForeignKeyConstraint(['window_id'], ['mdm_outbound_window.id']),
        sa.ForeignKeyConstraint(['pool_id'], ['mdm_offering_pool.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_id', 'window_id', 'pool_id', name='uq_mdm_student_selection')
    )
    op.create_index('ix_mdm_selection_student', 'mdm_outbound_selection', ['student_id'])
    op.create_index('ix_mdm_selection_status', 'mdm_outbound_selection', ['status'])

    # 5. Create mdm_audit_log table
    op.create_table('mdm_audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.String(50), nullable=False),
        sa.Column('window_id', sa.Integer(), nullable=True),
        sa.Column('student_id', sa.String(36), nullable=True),
        sa.Column('pool_id', sa.Integer(), nullable=True),
        sa.Column('old_value', sa.JSON(), nullable=True),
        sa.Column('new_value', sa.JSON(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('performed_by_id', sa.String(36), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(['window_id'], ['mdm_outbound_window.id']),
        sa.ForeignKeyConstraint(['student_id'], ['student_profile.student_id']),
        sa.ForeignKeyConstraint(['pool_id'], ['mdm_offering_pool.id']),
        sa.ForeignKeyConstraint(['performed_by_id'], ['user_master.user_id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mdm_audit_action', 'mdm_audit_log', ['action_type'])
    op.create_index('ix_mdm_audit_timestamp', 'mdm_audit_log', ['timestamp'])


def downgrade():
    op.drop_table('mdm_audit_log')
    op.drop_table('mdm_outbound_selection')
    op.drop_table('mdm_window_offering')
    op.drop_table('mdm_outbound_window')
    op.drop_table('mdm_offering_pool')
