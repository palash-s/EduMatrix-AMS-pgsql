"""superadmin onboarding flag

Revision ID: c1b7c6b2c9a1
Revises: f7a0e595a3e5
Create Date: 2026-01-06

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1b7c6b2c9a1'
down_revision = 'f7a0e595a3e5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user_master', schema=None) as batch_op:
        batch_op.add_column(sa.Column('onboarding_completed', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('user_master', schema=None) as batch_op:
        batch_op.drop_column('onboarding_completed')
