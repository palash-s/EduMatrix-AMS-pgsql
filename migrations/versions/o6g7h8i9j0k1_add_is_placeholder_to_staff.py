"""Add is_placeholder column to staff_profile for adjunct faculty

Revision ID: o6g7h8i9j0k1
Revises: n5f6g7h8i9j0
Create Date: 2026-01-29 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'o6g7h8i9j0k1'
down_revision = 'n5f6g7h8i9j0'
branch_labels = None
depends_on = None


def upgrade():
    # Add is_placeholder column for adjunct/external faculty created during bulk upload
    op.add_column('staff_profile', sa.Column('is_placeholder', sa.Boolean(), nullable=True, server_default='false'))


def downgrade():
    op.drop_column('staff_profile', 'is_placeholder')
