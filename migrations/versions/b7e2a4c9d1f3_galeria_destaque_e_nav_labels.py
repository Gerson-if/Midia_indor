"""galeria destaque e nav labels

Revision ID: b7e2a4c9d1f3
Revises: f418bbd27e42
Create Date: 2026-08-11 12:00:00.000000

Duas melhorias independentes, na mesma migração por serem pequenas:

1. gallery_items.is_featured -- permite ao admin destacar até 3 pontos
   como "os melhores" (ver GalleryItem.MAX_FEATURED). server_default
   garante que itens já existentes fiquem com o comportamento atual
   (nenhum destacado).

2. site_settings.*_nav_label -- o texto do menu (Vantagens/Telas/
   Clientes) era fixo no template; agora editável por página, igual ao
   título de cada seção (ver a5d713cf1948). server_default mantém o
   texto atual em instalações já em produção.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7e2a4c9d1f3'
down_revision = 'f418bbd27e42'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('gallery_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'is_featured', sa.Boolean(), nullable=False, server_default=sa.false(),
        ))

    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'services_nav_label', sa.String(length=40), nullable=False, server_default='Vantagens',
        ))
        batch_op.add_column(sa.Column(
            'gallery_nav_label', sa.String(length=40), nullable=False, server_default='Telas',
        ))
        batch_op.add_column(sa.Column(
            'testimonials_nav_label', sa.String(length=40), nullable=False, server_default='Clientes',
        ))

    # Remove os server_default após popular as linhas existentes, mesma
    # convenção das outras colunas -- o padrão passa a ser controlado só
    # pela aplicação a partir daqui.
    with op.batch_alter_table('gallery_items', schema=None) as batch_op:
        batch_op.alter_column('is_featured', server_default=None)

    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.alter_column('services_nav_label', server_default=None)
        batch_op.alter_column('gallery_nav_label', server_default=None)
        batch_op.alter_column('testimonials_nav_label', server_default=None)


def downgrade():
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.drop_column('testimonials_nav_label')
        batch_op.drop_column('gallery_nav_label')
        batch_op.drop_column('services_nav_label')

    with op.batch_alter_table('gallery_items', schema=None) as batch_op:
        batch_op.drop_column('is_featured')
