"""Add slot_label column to weekly_schedule for special slots

Revision ID: n5f6g7h8i9j0
Revises: m4e5f6g7h8i9
Create Date: 2026-01-29 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'n5f6g7h8i9j0'
down_revision = 'm4e5f6g7h8i9'
branch_labels = None
depends_on = None


def upgrade():
    # Add slot_label column for special slots (Library, Mentor Meeting, SCIL, etc.)
    op.add_column('weekly_schedule', sa.Column('slot_label', sa.String(100), nullable=True))


def downgrade():
    op.drop_column('weekly_schedule', 'slot_label')
