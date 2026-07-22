"""mensagem automática do botão whatsapp

Revision ID: 7d3f2a9b5c41
Revises: a1c9e4d7b210
Create Date: 2026-07-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7d3f2a9b5c41'
down_revision = 'a1c9e4d7b210'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'whatsapp_default_message',
            sa.String(length=300),
            nullable=True,
            server_default='Olá! Vi o site e gostaria de saber mais sobre anunciar em telas de mídia indoor.',
        ))

    # Remove o server_default após popular as linhas existentes, mesma
    # convenção das outras colunas desta tabela (o padrão passa a ser
    # controlado só pela aplicação).
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.alter_column('whatsapp_default_message', server_default=None)


def downgrade():
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.drop_column('whatsapp_default_message')
