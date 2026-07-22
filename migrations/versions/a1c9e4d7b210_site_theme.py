"""tema do sistema (claro/escuro)

Revision ID: a1c9e4d7b210
Revises: f7b8b5fafafc
Create Date: 2026-07-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c9e4d7b210'
down_revision = '6c4063ede536'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('theme', sa.String(length=10), nullable=False, server_default='dark'))

    # Remove o server_default após popular as linhas existentes, mesma
    # convenção das outras colunas desta tabela (o padrão passa a ser
    # controlado só pela aplicação).
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.alter_column('theme', server_default=None)


def downgrade():
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.drop_column('theme')
