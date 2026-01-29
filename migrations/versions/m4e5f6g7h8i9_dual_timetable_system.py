"""Dual Timetable System - Block Teaching + Regular Teaching

Adds support for:
- TimetablePeriod: Date range configuration for Block/Regular periods
- ScheduleChange: Runtime changes (substitutions, room changes, cancellations)
- HolidayCalendar: Holiday management
- LoadAllocationDetail: Detailed allocation from CSV upload
- New columns on TimetableVersion and WeeklySchedule

Revision ID: m4e5f6g7h8i9
Revises: l3d4e5f6g7h8
Create Date: 2026-01-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'm4e5f6g7h8i9'
down_revision = 'l3d4e5f6g7h8'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create timetable_period table
    op.create_table('timetable_period',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('timetable_type', sa.String(20), nullable=False),  # 'Block' or 'Regular'
        sa.Column('academic_year', sa.String(20), nullable=False),
        sa.Column('semester', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), server_default='Draft'),
        sa.Column('created_by_id', sa.String(36), sa.ForeignKey('staff_profile.staff_id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp()),
    )
    op.create_index('ix_timetable_period_type', 'timetable_period', ['timetable_type'])
    op.create_index('ix_timetable_period_dates', 'timetable_period', ['start_date', 'end_date'])

    # 2. Create schedule_change table
    op.create_table('schedule_change',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('change_type', sa.String(30), nullable=False),
        sa.Column('original_schedule_id', sa.Integer(), sa.ForeignKey('weekly_schedule.schedule_id'), nullable=True),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('specific_dates', sa.JSON(), nullable=True),
        sa.Column('original_values', sa.JSON(), nullable=True),
        sa.Column('new_values', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(20), server_default='Active'),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.String(36), sa.ForeignKey('staff_profile.staff_id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp()),
        sa.Column('approved_by_id', sa.String(36), sa.ForeignKey('staff_profile.staff_id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_schedule_change_type', 'schedule_change', ['change_type'])
    op.create_index('ix_schedule_change_dates', 'schedule_change', ['effective_from', 'effective_to'])
    op.create_index('ix_schedule_change_status', 'schedule_change', ['status'])

    # 3. Create holiday_calendar table
    op.create_table('holiday_calendar',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('type', sa.String(30), server_default='Full'),
        sa.Column('dept_id', sa.Integer(), sa.ForeignKey('department.dept_id'), nullable=True),
        sa.Column('academic_year', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp()),
    )
    op.create_index('ix_holiday_calendar_date', 'holiday_calendar', ['date'])
    op.create_index('ix_holiday_calendar_year', 'holiday_calendar', ['academic_year'])

    # 4. Create load_allocation_detail table
    op.create_table('load_allocation_detail',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('teaching_type', sa.String(20), nullable=False),
        sa.Column('subject_id', sa.Integer(), sa.ForeignKey('subject.subject_id'), nullable=False),
        sa.Column('teacher_id', sa.String(36), sa.ForeignKey('staff_profile.staff_id'), nullable=True),
        sa.Column('is_unassigned', sa.Boolean(), server_default='false'),
        sa.Column('session_type', sa.String(10), nullable=False),
        sa.Column('section_id', sa.Integer(), sa.ForeignKey('class_section.section_id'), nullable=True),
        sa.Column('class_level', sa.String(10), nullable=True),
        sa.Column('batch', sa.String(20), nullable=True),
        sa.Column('hours_per_week', sa.Integer(), server_default='1'),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('pattern', sa.String(10), nullable=True),
        sa.Column('academic_year', sa.String(20), nullable=True),
        sa.Column('semester', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp()),
        sa.Column('upload_batch_id', sa.String(36), nullable=True),
    )
    op.create_index('ix_load_allocation_teaching_type', 'load_allocation_detail', ['teaching_type'])
    op.create_index('ix_load_allocation_section', 'load_allocation_detail', ['section_id'])
    op.create_index('ix_load_allocation_teacher', 'load_allocation_detail', ['teacher_id'])

    # 5. Add columns to timetable_version
    op.add_column('timetable_version',
        sa.Column('timetable_type', sa.String(20), server_default='Regular')
    )
    op.add_column('timetable_version',
        sa.Column('period_id', sa.Integer(), sa.ForeignKey('timetable_period.id'), nullable=True)
    )
    op.create_index('ix_timetable_version_type', 'timetable_version', ['timetable_type'])

    # 6. Add column to weekly_schedule
    op.add_column('weekly_schedule',
        sa.Column('is_unassigned', sa.Boolean(), server_default='false')
    )


def downgrade():
    # Remove columns from existing tables
    op.drop_column('weekly_schedule', 'is_unassigned')
    op.drop_index('ix_timetable_version_type', table_name='timetable_version')
    op.drop_column('timetable_version', 'period_id')
    op.drop_column('timetable_version', 'timetable_type')

    # Drop new tables
    op.drop_index('ix_load_allocation_teacher', table_name='load_allocation_detail')
    op.drop_index('ix_load_allocation_section', table_name='load_allocation_detail')
    op.drop_index('ix_load_allocation_teaching_type', table_name='load_allocation_detail')
    op.drop_table('load_allocation_detail')

    op.drop_index('ix_holiday_calendar_year', table_name='holiday_calendar')
    op.drop_index('ix_holiday_calendar_date', table_name='holiday_calendar')
    op.drop_table('holiday_calendar')

    op.drop_index('ix_schedule_change_status', table_name='schedule_change')
    op.drop_index('ix_schedule_change_dates', table_name='schedule_change')
    op.drop_index('ix_schedule_change_type', table_name='schedule_change')
    op.drop_table('schedule_change')

    op.drop_index('ix_timetable_period_dates', table_name='timetable_period')
    op.drop_index('ix_timetable_period_type', table_name='timetable_period')
    op.drop_table('timetable_period')
