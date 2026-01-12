"""MDM/OE Subject Integration - Bridge MDM courses to regular infrastructure

Revision ID: j1b2c3d4e5f6
Revises: i0a1b2c3d4e5
Create Date: 2026-01-09 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'j1b2c3d4e5f6'
down_revision = 'i0a1b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add MDM/OE columns to subject table
    with op.batch_alter_table('subject', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_mdm_oe', sa.Boolean(), nullable=True, server_default=sa.false()))
        batch_op.add_column(sa.Column('mdm_pool_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('mdm_direction', sa.String(10), nullable=True))
        batch_op.create_foreign_key('fk_subject_mdm_pool', 'mdm_offering_pool', ['mdm_pool_id'], ['id'])
    
    # 2. Add virtual section support to class_section
    with op.batch_alter_table('class_section', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_virtual', sa.Boolean(), nullable=True, server_default=sa.false()))
        batch_op.add_column(sa.Column('mdm_pool_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_section_mdm_pool', 'mdm_offering_pool', ['mdm_pool_id'], ['id'])
    
    # 3. Create indexes for efficient queries
    op.create_index('ix_subject_is_mdm_oe', 'subject', ['is_mdm_oe'], unique=False)
    op.create_index('ix_subject_mdm_pool_id', 'subject', ['mdm_pool_id'], unique=False)
    op.create_index('ix_class_section_is_virtual', 'class_section', ['is_virtual'], unique=False)


def downgrade():
    # Drop indexes
    op.drop_index('ix_class_section_is_virtual', table_name='class_section')
    op.drop_index('ix_subject_mdm_pool_id', table_name='subject')
    op.drop_index('ix_subject_is_mdm_oe', table_name='subject')
    
    # Drop class_section columns
    with op.batch_alter_table('class_section', schema=None) as batch_op:
        batch_op.drop_constraint('fk_section_mdm_pool', type_='foreignkey')
        batch_op.drop_column('mdm_pool_id')
        batch_op.drop_column('is_virtual')
    
    # Drop subject columns
    with op.batch_alter_table('subject', schema=None) as batch_op:
        batch_op.drop_constraint('fk_subject_mdm_pool', type_='foreignkey')
        batch_op.drop_column('mdm_direction')
        batch_op.drop_column('mdm_pool_id')
        batch_op.drop_column('is_mdm_oe')
