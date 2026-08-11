from app.models import Service, Tenant, TenantDomain, User, UserRole
from tests.conftest import login


def login_superadmin(client, email, password):
    return client.post(
        "/super/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


# ------------------------------------------------------------------ #
# Acesso ao painel
# ------------------------------------------------------------------ #
def test_superadmin_login_and_dashboard(client, super_admin_user):
    resp = login_superadmin(client, "superadmin@teste.com", "SenhaForte123!")
    assert resp.status_code == 200
    resp = client.get("/super/")
    assert resp.status_code == 200
    assert "Páginas" in resp.get_data(as_text=True)


def test_regular_admin_cannot_access_superadmin_panel(client, admin_user):
    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.get("/super/")
    assert resp.status_code == 403


def test_superadmin_cannot_login_via_tenant_login(client, super_admin_user):
    """O super admin não pertence a nenhuma página -- não faz sentido
    (nem é permitido) ele entrar pelo /login comum de uma página."""
    resp = client.post(
        "/login",
        data={"email": "superadmin@teste.com", "password": "SenhaForte123!"},
    )
    assert resp.status_code == 200
    assert b"incorretos" in resp.data or resp.status_code == 200


def test_anonymous_redirected_to_superadmin_login(client):
    resp = client.get("/super/", follow_redirects=True)
    assert resp.status_code == 200
    assert "Super Admin" in resp.get_data(as_text=True)


# ------------------------------------------------------------------ #
# Criar / gerenciar páginas
# ------------------------------------------------------------------ #
def test_superadmin_creates_tenant_with_owner_and_domain(client, super_admin_user, db):
    login_superadmin(client, "superadmin@teste.com", "SenhaForte123!")
    resp = client.post(
        "/super/paginas/nova",
        data={
            "name": "Cliente Novo",
            "slug": "",
            "domain": "clientenovo.com.br",
            "owner_name": "Dono Cliente",
            "owner_email": "dono@clientenovo.com.br",
            "owner_password": "SenhaForte123!",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    t = Tenant.query.filter_by(name="Cliente Novo").first()
    assert t is not None
    assert t.owner_user is not None
    assert t.owner_user.email == "dono@clientenovo.com.br"
    assert t.owner_user.role == UserRole.ADMIN
    domain = TenantDomain.query.filter_by(tenant_id=t.id).first()
    assert domain.domain == "clientenovo.com.br"
    assert domain.is_primary is True


def test_superadmin_creates_tenant_with_demo_content_by_default(client, super_admin_user, db):
    """
    Página nova deve vir com um modelo pronto (serviços, galeria,
    depoimentos, parceiros, textos do Hero) em vez de em branco -- o
    seletor "Modelo de conteúdo inicial" vem em "midia_indoor" por padrão.
    """
    from app.models import GalleryItem, Partner, Service, SiteSettings, Testimonial

    login_superadmin(client, "superadmin@teste.com", "SenhaForte123!")
    resp = client.post(
        "/super/paginas/nova",
        data={
            "name": "Cliente Com Modelo",
            "slug": "",
            "domain": "",
            "owner_name": "Dono Cliente",
            "owner_email": "dono2@clientenovo.com.br",
            "owner_password": "SenhaForte123!",
            "template": "midia_indoor",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    t = Tenant.query.filter_by(name="Cliente Com Modelo").first()
    assert t is not None
    assert Service.query.filter_by(tenant_id=t.id).count() > 0
    assert GalleryItem.query.filter_by(tenant_id=t.id).count() > 0
    assert Testimonial.query.filter_by(tenant_id=t.id).count() > 0
    assert Partner.query.filter_by(tenant_id=t.id).count() > 0
    settings = SiteSettings.get_solo(tenant_id=t.id)
    assert settings.hero_title


def test_superadmin_creates_tenant_with_barbearia_template(client, super_admin_user, db):
    """Escolhendo outro modelo (ex.: Barbearia), o conteúdo semeado deve ser o desse nicho, não o de mídia indoor."""
    from app.models import Service, SiteSettings

    login_superadmin(client, "superadmin@teste.com", "SenhaForte123!")
    resp = client.post(
        "/super/paginas/nova",
        data={
            "name": "Barbearia do Zé",
            "slug": "",
            "domain": "",
            "owner_name": "Zé",
            "owner_email": "ze@barbearia.com.br",
            "owner_password": "SenhaForte123!",
            "template": "barbearia",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    t = Tenant.query.filter_by(name="Barbearia do Zé").first()
    assert t is not None
    titles = {s.title for s in Service.query.filter_by(tenant_id=t.id).all()}
    assert "Corte Masculino" in titles
    assert "Mídia em Elevadores" not in titles
    settings = SiteSettings.get_solo(tenant_id=t.id)
    assert settings.services_heading == "Nossos Serviços"


def test_superadmin_creates_tenant_without_demo_content_when_unchecked(client, super_admin_user, db):
    """Escolhendo "Não popular", a página deve continuar vazia (comportamento anterior)."""
    from app.models import Service

    login_superadmin(client, "superadmin@teste.com", "SenhaForte123!")
    resp = client.post(
        "/super/paginas/nova",
        data={
            "name": "Cliente Sem Modelo",
            "slug": "",
            "domain": "",
            "owner_name": "Dono Cliente",
            "owner_email": "dono3@clientenovo.com.br",
            "owner_password": "SenhaForte123!",
            "template": "none",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    t = Tenant.query.filter_by(name="Cliente Sem Modelo").first()
    assert t is not None
    assert Service.query.filter_by(tenant_id=t.id).count() == 0


def test_superadmin_block_and_unblock_tenant(client, super_admin_user, tenant, db):
    login_superadmin(client, "superadmin@teste.com", "SenhaForte123!")

    resp = client.post(
        f"/super/paginas/{tenant.id}/bloquear",
        data={"reason": "fatura em aberto"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(tenant)
    assert tenant.is_blocked is True
    assert tenant.blocked_reason == "fatura em aberto"

    resp = client.post(f"/super/paginas/{tenant.id}/desbloquear", follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(tenant)
    assert tenant.is_blocked is False


def test_superadmin_delete_tenant_requires_matching_slug(client, super_admin_user, tenant, admin_user, db):
    """Confirmação errada não apaga nada -- só o slug exato da página libera a exclusão."""
    login_superadmin(client, "superadmin@teste.com", "SenhaForte123!")

    resp = client.post(
        f"/super/paginas/{tenant.id}/excluir",
        data={"confirm_slug": "slug-errado"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Tenant.query.filter_by(id=tenant.id).first() is not None
    assert User.query.filter_by(id=admin_user.id).first() is not None


def test_superadmin_delete_tenant_removes_everything(client, super_admin_user, tenant, admin_user, db):
    """
    Excluir a página remove o tenant, seus usuários e todo o conteúdo
    (serviços, propostas...), mas preserva o log de auditoria (só
    desvinculado -- tenant_id/user_id viram NULL).
    """
    from app.models import AuditLog, Service
    from app.utils.decorators import log_action

    # Capturados antes da exclusão: os objetos ORM expiram após o commit
    # que apaga suas linhas, então acessar .id neles depois estouraria
    # ObjectDeletedError.
    tenant_id = tenant.id
    tenant_slug = tenant.slug
    admin_user_id = admin_user.id

    service = Service(tenant_id=tenant_id, title="Servico do Cliente", description="d", display_order=1)
    db.session.add(service)
    log_action("service.created", entity_type="Service", entity_id=1, tenant_id=tenant_id, description="teste")
    db.session.commit()

    login_superadmin(client, "superadmin@teste.com", "SenhaForte123!")
    resp = client.post(
        f"/super/paginas/{tenant_id}/excluir",
        data={"confirm_slug": tenant_slug},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    assert Tenant.query.filter_by(id=tenant_id).first() is None
    assert User.query.filter_by(id=admin_user_id).first() is None
    assert Service.query.filter_by(tenant_id=tenant_id).count() == 0

    old_log = AuditLog.query.filter_by(action="service.created").first()
    assert old_log is not None
    assert old_log.tenant_id is None

    delete_log = AuditLog.query.filter_by(action="tenant.deleted").first()
    assert delete_log is not None
    assert tenant_slug in delete_log.description


def test_regular_admin_cannot_delete_tenant(client, admin_user, tenant, db):
    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.post(f"/super/paginas/{tenant.id}/excluir", data={"confirm_slug": tenant.slug})
    assert resp.status_code in (302, 403)
    assert Tenant.query.filter_by(id=tenant.id).first() is not None


# ------------------------------------------------------------------ #
# Efeitos do bloqueio: público cai, painel do próprio admin continua
# ------------------------------------------------------------------ #
def test_blocked_tenant_hides_public_site_without_revealing_reason(client, admin_user, tenant, db):
    tenant.status = __import__("app.models", fromlist=["TenantStatus"]).TenantStatus.BLOCKED
    tenant.blocked_reason = "inadimplência - não divulgar"
    db.session.commit()

    resp = client.get("/")
    assert resp.status_code == 503
    html = resp.get_data(as_text=True)
    assert "inadimplência" not in html
    assert "não divulgar" not in html
    # mensagem amigável (avisa que o responsável já está ciente), sem
    # revelar o motivo real do bloqueio
    assert "Esta página deu uma pausa" in html


def test_blocked_tenant_admin_can_still_login_and_see_notice(client, admin_user, tenant, db):
    from app.models import TenantStatus

    tenant.status = TenantStatus.BLOCKED
    tenant.blocked_reason = "fatura de julho em aberto"
    db.session.commit()

    resp = login(client, "admin@teste.com", "SenhaForte123!")
    assert resp.status_code == 200

    resp = client.get("/admin/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "bloqueada" in html.lower()
    assert "fatura de julho em aberto" in html


# ------------------------------------------------------------------ #
# Isolamento entre páginas (multi-tenant)
# ------------------------------------------------------------------ #
def test_unknown_domain_shows_generic_unavailable_page(client):
    resp = client.get("/", headers={"Host": "dominio-nao-cadastrado.example.com"})
    assert resp.status_code == 404
    assert "Nada por aqui ainda" in resp.get_data(as_text=True)


def test_content_is_isolated_between_tenants(client, db, tenant, other_tenant):
    Service(tenant_id=tenant.id, title="Serviço A", description="desc", display_order=0)
    svc_a = Service(tenant_id=tenant.id, title="Serviço A", description="desc", display_order=0)
    svc_b = Service(tenant_id=other_tenant.id, title="Serviço B", description="desc", display_order=0)
    db.session.add_all([svc_a, svc_b])
    db.session.commit()

    resp = client.get("/", headers={"Host": "localhost"})
    html = resp.get_data(as_text=True)
    assert "Serviço A" in html
    assert "Serviço B" not in html

    resp = client.get("/", headers={"Host": "outra.localhost"})
    html = resp.get_data(as_text=True)
    assert "Serviço B" in html
    assert "Serviço A" not in html


def test_user_cannot_login_on_another_tenants_domain(client, db, tenant, other_tenant):
    user = User(name="Admin A", email="admina@teste.com", role=UserRole.ADMIN, tenant_id=tenant.id)
    user.set_password("SenhaForte123!")
    db.session.add(user)
    db.session.commit()

    # Credenciais corretas, mas domínio de OUTRA página -> não autentica.
    resp = client.post(
        "/login",
        data={"email": "admina@teste.com", "password": "SenhaForte123!"},
        headers={"Host": "outra.localhost"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "incorretos" in resp.get_data(as_text=True).lower()

    # No domínio certo, funciona normalmente.
    resp = client.post(
        "/login",
        data={"email": "admina@teste.com", "password": "SenhaForte123!"},
        headers={"Host": "localhost"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Visão Geral" in resp.get_data(as_text=True)
