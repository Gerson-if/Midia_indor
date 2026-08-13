"""page views (analytics do site)

Revision ID: e4b8f2a7c9d1
Revises: d2a9c6f1e5b3
Create Date: 2026-08-13 10:00:00.000000

Nova tabela page_views: alimenta o painel de "Visitas" do dashboard do
admin (visualizações, tempo médio na página e origem do tráfego). Cada
linha é uma visualização de página do site público, escrita pelo backend
(app/services/analytics.py) -- sem dado pessoal, só um identificador de
visitante aleatório (cookie "nx_vid") pra contar visitantes únicos.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e4b8f2a7c9d1'
down_revision = 'd2a9c6f1e5b3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'page_views',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('path', sa.String(length=255), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('referrer_source', sa.String(length=80), nullable=True),
        sa.Column('referrer_host', sa.String(length=255), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_page_views_tenant_id', 'page_views', ['tenant_id'])
    op.create_index('ix_page_views_session_id', 'page_views', ['session_id'])
    op.create_index('ix_page_views_created_at', 'page_views', ['created_at'])


def downgrade():
    op.drop_index('ix_page_views_created_at', table_name='page_views')
    op.drop_index('ix_page_views_session_id', table_name='page_views')
    op.drop_index('ix_page_views_tenant_id', table_name='page_views')
    op.drop_table('page_views')
