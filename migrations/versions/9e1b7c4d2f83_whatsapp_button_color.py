"""cor do botão de whatsapp

Revision ID: 9e1b7c4d2f83
Revises: 7d3f2a9b5c41
Create Date: 2026-07-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9e1b7c4d2f83'
down_revision = '7d3f2a9b5c41'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'whatsapp_button_color', sa.String(length=9), nullable=False, server_default='#25D366',
        ))

    # Remove o server_default após popular as linhas existentes, mesma
    # convenção das outras colunas desta tabela (o padrão passa a ser
    # controlado só pela aplicação).
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.alter_column('whatsapp_button_color', server_default=None)


def downgrade():
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.drop_column('whatsapp_button_color')
