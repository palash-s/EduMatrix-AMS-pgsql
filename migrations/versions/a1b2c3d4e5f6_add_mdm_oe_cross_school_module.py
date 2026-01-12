"""add mdm oe cross school module

Revision ID: a1b2c3d4e5f6
Revises: c1b7c6b2c9a1
Create Date: 2026-01-08

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'c1b7c6b2c9a1'
branch_labels = None
depends_on = None


def upgrade():
    # Add is_mdm_oe_coordinator flag to staff_profile
    with op.batch_alter_table('staff_profile', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_mdm_oe_coordinator', sa.Boolean(), nullable=False, server_default=sa.false()))
    
    # Create cross_school_offering table
    op.create_table(
        'cross_school_offering',
        sa.Column('offering_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('type', sa.String(length=10), nullable=False),  # MDM or OE
        sa.Column('direction', sa.String(length=10), nullable=False),  # Inbound or Outbound
        sa.Column('credits', sa.Integer(), nullable=False),
        sa.Column('capacity', sa.Integer(), nullable=False),
        sa.Column('host_school_id', sa.Integer(), nullable=True),
        sa.Column('host_school_name', sa.String(length=200), nullable=True),
        sa.Column('assigned_faculty_id', sa.String(length=36), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('schedule_pattern', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='Draft'),
        sa.Column('exclude_from_load', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('offering_id'),
        sa.ForeignKeyConstraint(['assigned_faculty_id'], ['staff_profile.staff_id'], ),
        sa.UniqueConstraint('code')
    )
    
    # Create external_student_profile table
    op.create_table(
        'external_student_profile',
        sa.Column('external_id', sa.Integer(), nullable=False),
        sa.Column('full_name', sa.String(length=100), nullable=False),
        sa.Column('roll_number', sa.String(length=50), nullable=False),
        sa.Column('email', sa.String(length=100), nullable=True),
        sa.Column('home_school_id', sa.Integer(), nullable=True),
        sa.Column('home_school_name', sa.String(length=200), nullable=True),
        sa.Column('department_name', sa.String(length=100), nullable=True),
        sa.Column('enrolled_offering_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='Enrolled'),
        sa.Column('enrolled_on', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('external_id'),
        sa.ForeignKeyConstraint(['enrolled_offering_id'], ['cross_school_offering.offering_id'], )
    )
    
    # Create cross_school_enrollment table
    op.create_table(
        'cross_school_enrollment',
        sa.Column('enrollment_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.String(length=36), nullable=False),
        sa.Column('offering_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='Enrolled'),
        sa.Column('external_marks', sa.Float(), nullable=True),
        sa.Column('external_grade', sa.String(length=5), nullable=True),
        sa.Column('enrolled_on', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('completed_on', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('enrollment_id'),
        sa.ForeignKeyConstraint(['student_id'], ['student_profile.student_id'], ),
        sa.ForeignKeyConstraint(['offering_id'], ['cross_school_offering.offering_id'], )
    )
    
    # Extend ca_marks table to support external students and cross-school offerings
    with op.batch_alter_table('ca_marks', schema=None) as batch_op:
        # Make student_id nullable (for external students)
        batch_op.alter_column('student_id', existing_type=sa.String(36), nullable=True)
        # Make subject_id nullable (for cross-school offerings)
        batch_op.alter_column('subject_id', existing_type=sa.Integer(), nullable=True)
        # Make section_id nullable (for external students)
        batch_op.alter_column('section_id', existing_type=sa.Integer(), nullable=True)
        
        # Add new columns
        batch_op.add_column(sa.Column('external_student_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('cross_school_offering_id', sa.Integer(), nullable=True))
        
        # Add foreign keys
        batch_op.create_foreign_key(
            'fk_ca_marks_external_student',
            'external_student_profile',
            ['external_student_id'],
            ['external_id']
        )
        batch_op.create_foreign_key(
            'fk_ca_marks_cross_school_offering',
            'cross_school_offering',
            ['cross_school_offering_id'],
            ['offering_id']
        )
    
    # Extend attendance_transaction table to support external students
    with op.batch_alter_table('attendance_transaction', schema=None) as batch_op:
        # Make student_id nullable (for external students)
        batch_op.alter_column('student_id', existing_type=sa.String(36), nullable=True)
        
        # Add new column
        batch_op.add_column(sa.Column('external_student_id', sa.Integer(), nullable=True))
        
        # Add foreign key
        batch_op.create_foreign_key(
            'fk_attendance_external_student',
            'external_student_profile',
            ['external_student_id'],
            ['external_id']
        )


def downgrade():
    # Drop foreign keys and columns from attendance_transaction
    with op.batch_alter_table('attendance_transaction', schema=None) as batch_op:
        batch_op.drop_constraint('fk_attendance_external_student', type_='foreignkey')
        batch_op.drop_column('external_student_id')
        batch_op.alter_column('student_id', existing_type=sa.String(36), nullable=False)
    
    # Drop foreign keys and columns from ca_marks
    with op.batch_alter_table('ca_marks', schema=None) as batch_op:
        batch_op.drop_constraint('fk_ca_marks_cross_school_offering', type_='foreignkey')
        batch_op.drop_constraint('fk_ca_marks_external_student', type_='foreignkey')
        batch_op.drop_column('cross_school_offering_id')
        batch_op.drop_column('external_student_id')
        batch_op.alter_column('section_id', existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column('subject_id', existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column('student_id', existing_type=sa.String(36), nullable=False)
    
    # Drop tables
    op.drop_table('cross_school_enrollment')
    op.drop_table('external_student_profile')
    op.drop_table('cross_school_offering')
    
    # Drop is_mdm_oe_coordinator column
    with op.batch_alter_table('staff_profile', schema=None) as batch_op:
        batch_op.drop_column('is_mdm_oe_coordinator')
