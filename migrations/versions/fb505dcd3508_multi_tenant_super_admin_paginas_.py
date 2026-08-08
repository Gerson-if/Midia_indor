"""multi-tenant: super admin, paginas, dominios

Revision ID: fb505dcd3508
Revises: 4a7c2e91b6df
Create Date: 2026-08-08 11:06:38.971443

Transforma o sistema, antes single-tenant (um site só), em multi-tenant
(várias "páginas" de clientes, geridas por um super admin). Se o banco já
tem dados (deploy existente rodando em produção), essa migração:

  1. Cria as tabelas tenants/tenant_domains;
  2. Cria um tenant "default" (migra o conteúdo já existente para ele);
  3. Preenche tenant_id em todas as linhas já existentes com esse tenant;
  4. Só então torna as colunas tenant_id obrigatórias (NOT NULL).

Assim, um banco vazio (instalação nova) e um banco com conteúdo real
(upgrade de uma instalação existente) migram da mesma forma, sem perda
de dados e sem quebrar em nenhum dos dois casos.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fb505dcd3508'
down_revision = '4a7c2e91b6df'
branch_labels = None
depends_on = None


# Tabelas de conteúdo que pertencem a exatamente um tenant (NOT NULL depois
# do backfill).
CONTENT_TABLES = [
    "custom_section_items",
    "custom_sections",
    "gallery_items",
    "partners",
    "proposals",
    "services",
    "site_settings",
    "testimonials",
]


def upgrade():
    # ---- 1) Tabelas novas: tenants / tenant_domains ----
    op.create_table('tenants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('slug', sa.String(length=140), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'BLOCKED', name='tenant_status'), nullable=False),
    sa.Column('blocked_reason', sa.String(length=300), nullable=True),
    sa.Column('blocked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('blocked_by_id', sa.Integer(), nullable=True),
    sa.Column('owner_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['blocked_by_id'], ['users.id'], name='fk_tenants_blocked_by', use_alter=True),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name='fk_tenants_owner_user', use_alter=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('owner_user_id')
    )
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tenants_slug'), ['slug'], unique=True)

    op.create_table('tenant_domains',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('domain', sa.String(length=255), nullable=False),
    sa.Column('is_primary', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('tenant_domains', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tenant_domains_domain'), ['domain'], unique=True)
        batch_op.create_index(batch_op.f('ix_tenant_domains_tenant_id'), ['tenant_id'], unique=False)

    # ---- 2) tenant_id como NULLABLE em todo mundo, por enquanto ----
    # (colunas obrigatórias exigiriam um valor em toda linha já existente,
    # que só existe depois do backfill do passo 4 abaixo.)
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_audit_logs_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key('fk_tenants_tenant_id', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('custom_section_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_custom_section_items_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key('fk_custom_section_items_tenant_id', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('custom_sections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))
        batch_op.drop_index('ix_custom_sections_slug')
        batch_op.create_index(batch_op.f('ix_custom_sections_slug'), ['slug'], unique=False)
        batch_op.create_index(batch_op.f('ix_custom_sections_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key('fk_custom_sections_tenant_id', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('gallery_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_gallery_items_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key('fk_gallery_items_tenant_id', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('partners', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_partners_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key('fk_partners_tenant_id', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('proposals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_proposals_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key('fk_proposals_tenant_id', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('services', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_services_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key('fk_services_tenant_id', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_site_settings_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key('fk_site_settings_tenant_id', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('testimonials', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_testimonials_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key('fk_testimonials_tenant_id', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))
        batch_op.alter_column('role',
               existing_type=sa.VARCHAR(length=6),
               type_=sa.Enum('SUPER_ADMIN', 'ADMIN', 'EDITOR', 'VIEWER', name='user_role'),
               existing_nullable=False)
        batch_op.create_index(batch_op.f('ix_users_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key('fk_users_tenant_id', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    # ---- 3) Backfill: se já existir conteúdo (instalação existente),
    # cria um tenant "default" e migra tudo para ele. Banco novo (sem
    # nenhuma linha em nenhuma tabela de conteúdo) simplesmente não cria
    # tenant nenhum -- a primeira página é criada normalmente depois,
    # via `flask create-admin` ou pelo painel do super admin. ----
    conn = op.get_bind()
    metadata = sa.MetaData()
    metadata.reflect(bind=conn, only=CONTENT_TABLES + ["users", "tenants"])

    has_existing_content = any(
        conn.execute(sa.select(sa.func.count()).select_from(metadata.tables[t])).scalar() > 0
        for t in CONTENT_TABLES
    )

    if has_existing_content:
        tenants_table = metadata.tables["tenants"]
        now = sa.func.now()
        result = conn.execute(
            tenants_table.insert().values(
                name="Página principal",
                slug="default",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
                version_id=1,
            )
        )
        default_tenant_id = result.inserted_primary_key[0]

        for table_name in CONTENT_TABLES:
            table = metadata.tables[table_name]
            conn.execute(table.update().values(tenant_id=default_tenant_id))

        users_table = metadata.tables["users"]
        conn.execute(
            users_table.update()
            .where(users_table.c.role != "SUPER_ADMIN")
            .values(tenant_id=default_tenant_id)
        )

        # Se houver um administrador, vira o "dono" formal da página no
        # painel do super admin (só um registro informativo -- login
        # continua funcionando independente disso).
        admin_row = conn.execute(
            sa.select(users_table.c.id)
            .where(users_table.c.role == "ADMIN")
            .order_by(users_table.c.id)
            .limit(1)
        ).first()
        if admin_row is not None:
            conn.execute(
                tenants_table.update()
                .where(tenants_table.c.id == default_tenant_id)
                .values(owner_user_id=admin_row[0])
            )

    # ---- 4) Agora que todo mundo tem tenant_id preenchido (ou a tabela
    # está vazia), torna a coluna obrigatória nas tabelas de conteúdo.
    # site_settings também ganha a restrição de unicidade por tenant
    # (1 linha de configuração por página) só agora, depois do backfill.
    for table_name in CONTENT_TABLES:
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('custom_sections', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_custom_sections_tenant_slug', ['tenant_id', 'slug'])

    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_site_settings_tenant', ['tenant_id'])
    # users.tenant_id continua NULLABLE de propósito (nulo = super admin).
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_users_tenant_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_users_tenant_id'))
        batch_op.alter_column('role',
               existing_type=sa.Enum('SUPER_ADMIN', 'ADMIN', 'EDITOR', 'VIEWER', name='user_role'),
               type_=sa.VARCHAR(length=6),
               existing_nullable=False)
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('testimonials', schema=None) as batch_op:
        batch_op.drop_constraint('fk_testimonials_tenant_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_testimonials_tenant_id'))
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.drop_constraint('fk_site_settings_tenant_id', type_='foreignkey')
        batch_op.drop_constraint('uq_site_settings_tenant', type_='unique')
        batch_op.drop_index(batch_op.f('ix_site_settings_tenant_id'))
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('services', schema=None) as batch_op:
        batch_op.drop_constraint('fk_services_tenant_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_services_tenant_id'))
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('proposals', schema=None) as batch_op:
        batch_op.drop_constraint('fk_proposals_tenant_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_proposals_tenant_id'))
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('partners', schema=None) as batch_op:
        batch_op.drop_constraint('fk_partners_tenant_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_partners_tenant_id'))
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('gallery_items', schema=None) as batch_op:
        batch_op.drop_constraint('fk_gallery_items_tenant_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_gallery_items_tenant_id'))
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('custom_sections', schema=None) as batch_op:
        batch_op.drop_constraint('fk_custom_sections_tenant_id', type_='foreignkey')
        batch_op.drop_constraint('uq_custom_sections_tenant_slug', type_='unique')
        batch_op.drop_index(batch_op.f('ix_custom_sections_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_custom_sections_slug'))
        batch_op.create_index('ix_custom_sections_slug', ['slug'], unique=1)
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('custom_section_items', schema=None) as batch_op:
        batch_op.drop_constraint('fk_custom_section_items_tenant_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_custom_section_items_tenant_id'))
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_audit_logs_tenant_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_audit_logs_tenant_id'))
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('tenant_domains', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tenant_domains_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_tenant_domains_domain'))

    op.drop_table('tenant_domains')
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tenants_slug'))

    op.drop_table('tenants')
    # ### end Alembic commands ###
