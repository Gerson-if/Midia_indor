import pytest

from app import create_app
from app.extensions import db as _db
from app.models import Tenant, TenantDomain, User, UserRole


@pytest.fixture()
def app():
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture(autouse=True)
def tenant(app, db):
    """
    Tenant (página) padrão usado pelos testes. O cliente de testes do
    Flask acessa com Host "localhost" por padrão -- por isso o domínio
    cadastrado aqui é "localhost", fazendo a resolução por domínio
    (app/utils/tenancy.py) funcionar nos testes sem nenhuma configuração
    extra.
    """
    t = Tenant(name="Empresa Teste", slug="empresa-teste")
    db.session.add(t)
    db.session.flush()
    db.session.add(TenantDomain(tenant_id=t.id, domain="localhost", is_primary=True))
    db.session.commit()
    return t


@pytest.fixture()
def other_tenant(app, db):
    """Um segundo tenant, usado para testar isolamento entre páginas."""
    t = Tenant(name="Outra Empresa", slug="outra-empresa")
    db.session.add(t)
    db.session.flush()
    db.session.add(TenantDomain(tenant_id=t.id, domain="outra.localhost", is_primary=True))
    db.session.commit()
    return t


@pytest.fixture()
def admin_user(app, db, tenant):
    user = User(name="Admin Teste", email="admin@teste.com", role=UserRole.ADMIN, tenant_id=tenant.id)
    user.set_password("SenhaForte123!")
    db.session.add(user)
    db.session.flush()
    tenant.owner_user_id = user.id
    db.session.commit()
    return user


@pytest.fixture()
def editor_user(app, db, tenant):
    user = User(name="Editor Teste", email="editor@teste.com", role=UserRole.EDITOR, tenant_id=tenant.id)
    user.set_password("SenhaForte123!")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def super_admin_user(app, db):
    user = User(name="Super Admin Teste", email="superadmin@teste.com", role=UserRole.SUPER_ADMIN, tenant_id=None)
    user.set_password("SenhaForte123!")
    db.session.add(user)
    db.session.commit()
    return user


def login(client, email, password):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )
