"""corrige enum user_role sem SUPER_ADMIN no postgres

Revision ID: a1a11918f060
Revises: a5d713cf1948
Create Date: 2026-08-10 21:01:14.699892

A migração fb505dcd3508 (multi-tenant) mudou users.role para
sa.Enum('SUPER_ADMIN', 'ADMIN', 'EDITOR', 'VIEWER', name='user_role')
via alter_column. Isso funciona em SQLite (o Enum é emulado como
VARCHAR + CHECK, recriado do zero pelo batch_alter_table), mas em
PostgreSQL "user_role" já existia como TYPE nativo -- criado pela
migração inicial só com ('ADMIN', 'EDITOR', 'VIEWER') -- e um
alter_column que referencia um Enum de mesmo nome não adiciona os
valores que faltam ao TYPE existente; só troca o tipo da coluna,
assumindo (incorretamente) que o TYPE já tem os valores certos.
Resultado em produção (Postgres): "flask create-superadmin" falha com
DataError "invalid input value for enum user_role: SUPER_ADMIN", já
que o TYPE no banco nunca ganhou esse valor.

Esta migração corrige isso adicionando o valor que falta diretamente
ao TYPE do Postgres. Não afeta SQLite (onde o valor já está correto
desde fb505dcd3508) nem instalações Postgres que, por algum motivo,
já tenham o valor (ADD VALUE IF NOT EXISTS é idempotente).
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a1a11918f060'
down_revision = 'a5d713cf1948'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    # ALTER TYPE ... ADD VALUE não pode rodar dentro da transação que o
    # Alembic normalmente usa para cada migração (mesmo em Postgres 12+,
    # que permite o comando em transação, o valor novo não pode ser
    # usado na mesma transação em que foi criado -- autocommit_block()
    # evita esse problema rodando este comando isolado, fora da
    # transação da migração).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'SUPER_ADMIN'")


def downgrade():
    # PostgreSQL não permite remover um valor de enum diretamente (exigiria
    # recriar o TYPE do zero e todas as colunas que o usam). Não é uma
    # operação segura de automatizar aqui -- o valor extra sobrando no
    # TYPE não quebra nada mesmo se o código for revertido para uma
    # versão anterior.
    pass
