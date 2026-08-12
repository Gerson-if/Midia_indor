"""recomendacoes estruturadas da galeria

Revision ID: d2a9c6f1e5b3
Revises: c3f6a1e8b4d7
Create Date: 2026-08-12 14:00:00.000000

Duas melhorias na página de detalhes do ponto (galeria):

1. "Recomendado para" deixa de ser um texto livre separado por vírgula
   (gallery_items.detail_tags) e vira uma tabela própria
   (gallery_recommendations), cadastrada dinamicamente pelo admin, com um
   ícone opcional por item.

2. "Tempo de retenção" deixa de ser texto livre (ex.: "45 min") e vira
   quantidade (detail_retention_value) + unidade (detail_retention_unit)
   -- o sistema já sabe o texto certo, o admin só aloca o número.

Os dados existentes são migrados automaticamente (melhor esforço): cada
tag vira uma recomendação sem ícone, e o texto de retenção é interpretado
para extrair o número e a unidade quando possível.
"""
import re

from alembic import op
import sqlalchemy as sa
from sqlalchemy import table, column


# revision identifiers, used by Alembic.
revision = 'd2a9c6f1e5b3'
down_revision = 'c3f6a1e8b4d7'
branch_labels = None
depends_on = None

_RETENTION_RE = re.compile(r'(\d+)\s*(h|hora|horas|min|minuto|minutos)?', re.IGNORECASE)


def upgrade():
    op.create_table(
        'gallery_recommendations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column(
            'gallery_item_id', sa.Integer(), sa.ForeignKey('gallery_items.id', ondelete='CASCADE'), nullable=False
        ),
        sa.Column('icon', sa.String(length=8), nullable=True),
        sa.Column('label', sa.String(length=80), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_gallery_recommendations_tenant_id', 'gallery_recommendations', ['tenant_id'])
    op.create_index('ix_gallery_recommendations_gallery_item_id', 'gallery_recommendations', ['gallery_item_id'])

    with op.batch_alter_table('gallery_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('detail_retention_value', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('detail_retention_unit', sa.String(length=10), nullable=True, server_default='min'))

    conn = op.get_bind()
    gallery_items = table(
        'gallery_items',
        column('id', sa.Integer),
        column('tenant_id', sa.Integer),
        column('detail_tags', sa.String),
        column('detail_retention_time', sa.String),
        column('detail_retention_value', sa.Integer),
        column('detail_retention_unit', sa.String),
    )
    gallery_recommendations = table(
        'gallery_recommendations',
        column('tenant_id', sa.Integer),
        column('gallery_item_id', sa.Integer),
        column('icon', sa.String),
        column('label', sa.String),
        column('display_order', sa.Integer),
    )

    rows = conn.execute(
        sa.select(
            gallery_items.c.id,
            gallery_items.c.tenant_id,
            gallery_items.c.detail_tags,
            gallery_items.c.detail_retention_time,
        )
    ).fetchall()

    for row in rows:
        if row.detail_tags:
            labels = [t.strip() for t in row.detail_tags.split(',') if t.strip()]
            for idx, label in enumerate(labels):
                conn.execute(
                    gallery_recommendations.insert().values(
                        tenant_id=row.tenant_id,
                        gallery_item_id=row.id,
                        icon=None,
                        label=label[:80],
                        display_order=idx,
                    )
                )
        if row.detail_retention_time:
            match = _RETENTION_RE.search(row.detail_retention_time)
            if match and match.group(1):
                unit_text = (match.group(2) or 'min').lower()
                unit = 'h' if unit_text.startswith('h') else 'min'
                conn.execute(
                    gallery_items.update()
                    .where(gallery_items.c.id == row.id)
                    .values(detail_retention_value=int(match.group(1)), detail_retention_unit=unit)
                )

    with op.batch_alter_table('gallery_items', schema=None) as batch_op:
        batch_op.alter_column('detail_retention_unit', server_default=None)
        batch_op.drop_column('detail_tags')
        batch_op.drop_column('detail_retention_time')


def downgrade():
    with op.batch_alter_table('gallery_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('detail_tags', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('detail_retention_time', sa.String(length=40), nullable=True))

    conn = op.get_bind()
    gallery_items = table(
        'gallery_items',
        column('id', sa.Integer),
        column('detail_tags', sa.String),
        column('detail_retention_time', sa.String),
        column('detail_retention_value', sa.Integer),
        column('detail_retention_unit', sa.String),
    )
    gallery_recommendations = table(
        'gallery_recommendations',
        column('gallery_item_id', sa.Integer),
        column('label', sa.String),
        column('display_order', sa.Integer),
    )

    item_rows = conn.execute(
        sa.select(gallery_items.c.id, gallery_items.c.detail_retention_value, gallery_items.c.detail_retention_unit)
    ).fetchall()
    for row in item_rows:
        rec_rows = conn.execute(
            sa.select(gallery_recommendations.c.label)
            .where(gallery_recommendations.c.gallery_item_id == row.id)
            .order_by(gallery_recommendations.c.display_order)
        ).fetchall()
        values = {}
        if rec_rows:
            values['detail_tags'] = ', '.join(r.label for r in rec_rows)[:300]
        if row.detail_retention_value is not None:
            values['detail_retention_time'] = f"{row.detail_retention_value} {row.detail_retention_unit or 'min'}"
        if values:
            conn.execute(gallery_items.update().where(gallery_items.c.id == row.id).values(**values))

    with op.batch_alter_table('gallery_items', schema=None) as batch_op:
        batch_op.drop_column('detail_retention_value')
        batch_op.drop_column('detail_retention_unit')

    op.drop_index('ix_gallery_recommendations_gallery_item_id', table_name='gallery_recommendations')
    op.drop_index('ix_gallery_recommendations_tenant_id', table_name='gallery_recommendations')
    op.drop_table('gallery_recommendations')
