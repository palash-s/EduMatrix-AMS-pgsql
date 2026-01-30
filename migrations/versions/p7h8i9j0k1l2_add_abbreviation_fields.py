"""Add abbreviation and enhanced allocation fields

Revision ID: p7h8i9j0k1l2
Revises: o6g7h8i9j0k1
Create Date: 2026-01-29

Adds:
- subject.abbreviation: For timetable slot lookup (e.g., OS, SE, CN)
- subject.category: Course category (PCC, ELECTIVE-I, etc.)
- subject.pattern: Pattern year (2021, 2023)
- staff_profile.abbreviation: Faculty abbreviation for timetable (PB, SH, JN)
- subject_allocation.session_type: L/T/P
- subject_allocation.target_batch: Batch for practical sessions
- subject_allocation.teaching_type: Regular/Block
- subject_allocation.faculty_abbreviation: For quick lookup
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p7h8i9j0k1l2'
down_revision = 'o6g7h8i9j0k1'
branch_labels = None
depends_on = None


def upgrade():
    # Subject table enhancements
    op.add_column('subject', sa.Column('abbreviation', sa.String(20), nullable=True))
    op.add_column('subject', sa.Column('category', sa.String(50), nullable=True))
    op.add_column('subject', sa.Column('pattern', sa.String(10), nullable=True))
    op.create_index('ix_subject_abbreviation', 'subject', ['abbreviation'])
    
    # Staff profile abbreviation
    op.add_column('staff_profile', sa.Column('abbreviation', sa.String(20), nullable=True))
    op.create_index('ix_staff_profile_abbreviation', 'staff_profile', ['abbreviation'])
    
    # SubjectAllocation enhancements
    op.add_column('subject_allocation', sa.Column('session_type', sa.String(10), nullable=True))
    op.add_column('subject_allocation', sa.Column('target_batch', sa.String(20), nullable=True))
    op.add_column('subject_allocation', sa.Column('teaching_type', sa.String(20), server_default='Regular'))
    op.add_column('subject_allocation', sa.Column('faculty_abbreviation', sa.String(20), nullable=True))
    
    # Make teacher_id nullable for "Respective Faculties" entries
    op.alter_column('subject_allocation', 'teacher_id', nullable=True)
    
    # Index for allocation lookups
    op.create_index('ix_allocation_lookup', 'subject_allocation', 
                    ['section_id', 'subject_id', 'session_type', 'target_batch'])


def downgrade():
    op.drop_index('ix_allocation_lookup', 'subject_allocation')
    op.drop_column('subject_allocation', 'faculty_abbreviation')
    op.drop_column('subject_allocation', 'teaching_type')
    op.drop_column('subject_allocation', 'target_batch')
    op.drop_column('subject_allocation', 'session_type')
    
    op.drop_index('ix_staff_profile_abbreviation', 'staff_profile')
    op.drop_column('staff_profile', 'abbreviation')
    
    op.drop_index('ix_subject_abbreviation', 'subject')
    op.drop_column('subject', 'pattern')
    op.drop_column('subject', 'category')
    op.drop_column('subject', 'abbreviation')
