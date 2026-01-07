"""hierarchy overlay

Revision ID: f7a0e595a3e5
Revises: f5a5a2b067f1
Create Date: 2026-01-06 09:09:27.795480

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7a0e595a3e5'
down_revision = 'f5a5a2b067f1'
branch_labels = None
depends_on = None


def upgrade():
    # Additive-only overlay changes (keep legacy schema intact).

    # Department: add optional link to Program + optional Dept Admin
    with op.batch_alter_table('department', schema=None) as batch_op:
        batch_op.add_column(sa.Column('program_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('dept_admin_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(batch_op.f('fk_department_program_id_program'), 'program', ['program_id'], ['id'])
        batch_op.create_foreign_key(batch_op.f('fk_department_dept_admin_id_staff_profile'), 'staff_profile', ['dept_admin_id'], ['staff_id'])

    # Program: add optional link to School (overlay)
    with op.batch_alter_table('program', schema=None) as batch_op:
        batch_op.add_column(sa.Column('school_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(batch_op.f('fk_program_school_id_school'), 'school', ['school_id'], ['id'])

    # Specialization: add optional dept_id + hod_id (overlay)
    with op.batch_alter_table('specialization', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dept_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('hod_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(batch_op.f('fk_specialization_dept_id_department'), 'department', ['dept_id'], ['dept_id'])
        batch_op.create_foreign_key(batch_op.f('fk_specialization_hod_id_staff_profile'), 'staff_profile', ['hod_id'], ['staff_id'])


def downgrade():
    with op.batch_alter_table('specialization', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_specialization_hod_id_staff_profile'), type_='foreignkey')
        batch_op.drop_constraint(batch_op.f('fk_specialization_dept_id_department'), type_='foreignkey')
        batch_op.drop_column('hod_id')
        batch_op.drop_column('dept_id')

    with op.batch_alter_table('program', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_program_school_id_school'), type_='foreignkey')
        batch_op.drop_column('school_id')

    with op.batch_alter_table('department', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_department_dept_admin_id_staff_profile'), type_='foreignkey')
        batch_op.drop_constraint(batch_op.f('fk_department_program_id_program'), type_='foreignkey')
        batch_op.drop_column('dept_admin_id')
        batch_op.drop_column('program_id')
