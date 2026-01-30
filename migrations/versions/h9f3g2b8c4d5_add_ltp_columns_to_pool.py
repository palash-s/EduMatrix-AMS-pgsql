"""Add L, T, P, credits columns to elective_subject_pool

Revision ID: h9f3g2b8c4d5
Revises: g8e2f1a7b9c3
Create Date: 2026-01-09 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h9f3g2b8c4d5'
down_revision = 'g8e2f1a7b9c3'
branch_labels = None
depends_on = None


def upgrade():
    # Add L, T, P, credits columns to elective_subject_pool for load calculation
    op.add_column('elective_subject_pool', sa.Column('l_count', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('elective_subject_pool', sa.Column('t_count', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('elective_subject_pool', sa.Column('p_count', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('elective_subject_pool', sa.Column('credits', sa.Integer(), nullable=True, server_default='3'))


def downgrade():
    op.drop_column('elective_subject_pool', 'credits')
    op.drop_column('elective_subject_pool', 'p_count')
    op.drop_column('elective_subject_pool', 't_count')
    op.drop_column('elective_subject_pool', 'l_count')
