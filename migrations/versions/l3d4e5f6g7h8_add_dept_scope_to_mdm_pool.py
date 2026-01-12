"""Add dept_id column to mdm_offering_pool for department scoping

Revision ID: l3d4e5f6g7h8
Revises: k2c3d4e5f6g7
Create Date: 2026-01-12

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'l3d4e5f6g7h8'
down_revision = 'k2c3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade():
    # Add dept_id column to mdm_offering_pool for department scoping
    op.add_column('mdm_offering_pool',
        sa.Column('dept_id', sa.Integer(), sa.ForeignKey('department.dept_id'), nullable=True)
    )

    # Create index for faster filtering by department
    op.create_index('ix_mdm_offering_pool_dept_id', 'mdm_offering_pool', ['dept_id'])


def downgrade():
    op.drop_index('ix_mdm_offering_pool_dept_id', table_name='mdm_offering_pool')
    op.drop_column('mdm_offering_pool', 'dept_id')
