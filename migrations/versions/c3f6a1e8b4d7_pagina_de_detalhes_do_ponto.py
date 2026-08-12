"""pagina de detalhes do ponto

Revision ID: c3f6a1e8b4d7
Revises: b7e2a4c9d1f3
Create Date: 2026-08-12 09:00:00.000000

Cada item da galeria pode opcionalmente ganhar uma página própria de
detalhes (texto sobre o ponto, tags de "recomendado para" e métricas
de fluxo/retenção/visibilidade) -- o admin decide item a item, via
has_detail_page. server_default garante que itens já existentes fiquem
com o comportamento atual (card estático, sem link).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3f6a1e8b4d7'
down_revision = 'b7e2a4c9d1f3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('gallery_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'has_detail_page', sa.Boolean(), nullable=False, server_default=sa.false(),
        ))
        batch_op.add_column(sa.Column('detail_description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('detail_tags', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('detail_monthly_reach', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('detail_retention_time', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('detail_visibility_percent', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('detail_cta_message', sa.String(length=300), nullable=True))

    with op.batch_alter_table('gallery_items', schema=None) as batch_op:
        batch_op.alter_column('has_detail_page', server_default=None)


def downgrade():
    with op.batch_alter_table('gallery_items', schema=None) as batch_op:
        batch_op.drop_column('detail_cta_message')
        batch_op.drop_column('detail_visibility_percent')
        batch_op.drop_column('detail_retention_time')
        batch_op.drop_column('detail_monthly_reach')
        batch_op.drop_column('detail_tags')
        batch_op.drop_column('detail_description')
        batch_op.drop_column('has_detail_page')
