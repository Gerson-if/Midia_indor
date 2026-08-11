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
