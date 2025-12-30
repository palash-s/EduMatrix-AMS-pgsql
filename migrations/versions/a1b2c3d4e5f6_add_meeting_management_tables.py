"""Add meeting management tables for NAAC compliance

Revision ID: a1b2c3d4e5f6
Revises: cf8f089488d4
Create Date: 2025-12-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'cf8f089488d4'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to mentor_meeting table
    op.add_column('mentor_meeting', sa.Column('venue', sa.String(100), nullable=True))
    op.add_column('mentor_meeting', sa.Column('discussion_points', sa.Text(), nullable=True))
    op.add_column('mentor_meeting', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('mentor_meeting', sa.Column('completed_at', sa.DateTime(), nullable=True))

    # Create meeting_attendance table
    op.create_table('meeting_attendance',
        sa.Column('attendance_id', sa.Integer(), nullable=False),
        sa.Column('meeting_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.String(36), nullable=False),
        sa.Column('attended', sa.Boolean(), nullable=True, default=False),
        sa.Column('remarks', sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(['meeting_id'], ['mentor_meeting.meeting_id'], ),
        sa.ForeignKeyConstraint(['student_id'], ['student_profile.student_id'], ),
        sa.PrimaryKeyConstraint('attendance_id')
    )

    # Create meeting_issue table
    op.create_table('meeting_issue',
        sa.Column('issue_id', sa.Integer(), nullable=False),
        sa.Column('meeting_id', sa.Integer(), nullable=False),
        sa.Column('raised_by_student_id', sa.String(36), nullable=True),
        sa.Column('issue_description', sa.Text(), nullable=False),
        sa.Column('category', sa.String(50), nullable=True, default='General'),
        sa.Column('action_taken', sa.Text(), nullable=True),
        sa.Column('action_status', sa.String(20), nullable=True, default='Pending'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['meeting_id'], ['mentor_meeting.meeting_id'], ),
        sa.ForeignKeyConstraint(['raised_by_student_id'], ['student_profile.student_id'], ),
        sa.PrimaryKeyConstraint('issue_id')
    )


def downgrade():
    op.drop_table('meeting_issue')
    op.drop_table('meeting_attendance')
    op.drop_column('mentor_meeting', 'completed_at')
    op.drop_column('mentor_meeting', 'summary')
    op.drop_column('mentor_meeting', 'discussion_points')
    op.drop_column('mentor_meeting', 'venue')
