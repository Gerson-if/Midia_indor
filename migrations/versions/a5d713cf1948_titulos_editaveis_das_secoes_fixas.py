"""titulos editaveis das secoes fixas

Revision ID: a5d713cf1948
Revises: fb505dcd3508
Create Date: 2026-08-10 20:23:32.796703

Título/subtítulo das seções fixas do site (Vantagens, Galeria,
Depoimentos, Contato) eram fixos no template — passam a viver em
site_settings, editáveis pelo admin, igual às seções personalizadas.
server_default garante que instalações já em produção mantenham o
mesmo texto exibido hoje (sem isso, ALTER TABLE ADD COLUMN NOT NULL
falharia em Postgres com linhas já existentes).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a5d713cf1948'
down_revision = 'fb505dcd3508'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'services_heading', sa.String(length=150), nullable=False,
            server_default='Por que anunciar conosco?',
        ))
        batch_op.add_column(sa.Column(
            'services_subtitle', sa.String(length=300), nullable=True,
            server_default='Gerenciamento inteligente e telas nos pontos mais estratégicos da cidade.',
        ))
        batch_op.add_column(sa.Column(
            'gallery_heading', sa.String(length=150), nullable=False,
            server_default='Nossos Pontos',
        ))
        batch_op.add_column(sa.Column(
            'gallery_subtitle', sa.String(length=300), nullable=True,
            server_default='Confira os locais onde sua marca será exibida.',
        ))
        batch_op.add_column(sa.Column(
            'testimonials_heading', sa.String(length=150), nullable=False,
            server_default='Marcas que confiam',
        ))
        batch_op.add_column(sa.Column(
            'contact_heading', sa.String(length=150), nullable=False,
            server_default='Pronto para anunciar?',
        ))

    # Remove os server_default após popular as linhas existentes, mesma
    # convenção das outras colunas desta tabela (o padrão passa a ser
    # controlado só pela aplicação).
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.alter_column('services_heading', server_default=None)
        batch_op.alter_column('services_subtitle', server_default=None)
        batch_op.alter_column('gallery_heading', server_default=None)
        batch_op.alter_column('gallery_subtitle', server_default=None)
        batch_op.alter_column('testimonials_heading', server_default=None)
        batch_op.alter_column('contact_heading', server_default=None)


def downgrade():
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.drop_column('contact_heading')
        batch_op.drop_column('testimonials_heading')
        batch_op.drop_column('gallery_subtitle')
        batch_op.drop_column('gallery_heading')
        batch_op.drop_column('services_subtitle')
        batch_op.drop_column('services_heading')
