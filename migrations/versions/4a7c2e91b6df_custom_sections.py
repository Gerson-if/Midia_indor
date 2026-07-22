"""seções personalizadas do site (criadas pelo admin)

Revision ID: 4a7c2e91b6df
Revises: 9e1b7c4d2f83
Create Date: 2026-07-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4a7c2e91b6df'
down_revision = '9e1b7c4d2f83'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'custom_sections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('slug', sa.String(length=60), nullable=False),
        sa.Column('nav_label', sa.String(length=60), nullable=False),
        sa.Column('heading', sa.String(length=150), nullable=False),
        sa.Column('subtitle', sa.String(length=300), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    with op.batch_alter_table('custom_sections', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_custom_sections_slug'), ['slug'], unique=True)

    op.create_table(
        'custom_section_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('description', sa.String(length=400), nullable=True),
        sa.Column('image_path', sa.String(length=255), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['section_id'], ['custom_sections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('custom_section_items', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_custom_section_items_section_id'), ['section_id'], unique=False
        )


def downgrade():
    with op.batch_alter_table('custom_section_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_custom_section_items_section_id'))
    op.drop_table('custom_section_items')

    with op.batch_alter_table('custom_sections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_custom_sections_slug'))
    op.drop_table('custom_sections')
