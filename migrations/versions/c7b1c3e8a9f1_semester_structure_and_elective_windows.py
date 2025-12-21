"""Semester structure and elective windows

Revision ID: c7b1c3e8a9f1
Revises: aba0eb65ab1f
Create Date: 2025-12-14

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7b1c3e8a9f1'
down_revision = 'aba0eb65ab1f'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table('elective_window'):
        op.create_table(
            'elective_window',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('section_id', sa.Integer(), nullable=False),
            sa.Column('target_semester_no', sa.Integer(), nullable=False),
            sa.Column('bucket', sa.String(length=50), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=True),
            sa.Column('min_batch_size', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('closed_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['section_id'], ['class_section.section_id'], name=op.f('fk_elective_window_section_id_class_section')),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_elective_window')),
        )

    if not insp.has_table('semester_course_structure'):
        op.create_table(
            'semester_course_structure',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('section_id', sa.Integer(), nullable=False),
            sa.Column('semester_no', sa.Integer(), nullable=False),
            sa.Column('subject_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['section_id'], ['class_section.section_id'], name=op.f('fk_semester_course_structure_section_id_class_section')),
            sa.ForeignKeyConstraint(['subject_id'], ['subject.subject_id'], name=op.f('fk_semester_course_structure_subject_id_subject')),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_semester_course_structure')),
        )

    eo_cols = [c['name'] for c in insp.get_columns('elective_offering')]
    if 'window_id' not in eo_cols:
        op.add_column('elective_offering', sa.Column('window_id', sa.Integer(), nullable=True))
        try:
            op.create_foreign_key(op.f('fk_elective_offering_window_id_elective_window'), 'elective_offering', 'elective_window', ['window_id'], ['id'])
        except Exception:
            # SQLite may already have the constraint from db.create_all
            pass

    se_cols = [c['name'] for c in insp.get_columns('student_elective')]
    if 'window_id' not in se_cols:
        op.add_column('student_elective', sa.Column('window_id', sa.Integer(), nullable=True))
        try:
            op.create_foreign_key(op.f('fk_student_elective_window_id_elective_window'), 'student_elective', 'elective_window', ['window_id'], ['id'])
        except Exception:
            pass


def downgrade():
    op.drop_constraint(op.f('fk_student_elective_window_id_elective_window'), 'student_elective', type_='foreignkey')
    op.drop_column('student_elective', 'window_id')

    op.drop_constraint(op.f('fk_elective_offering_window_id_elective_window'), 'elective_offering', type_='foreignkey')
    op.drop_column('elective_offering', 'window_id')

    op.drop_table('semester_course_structure')
    op.drop_table('elective_window')
