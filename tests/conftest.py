import pytest

from app import create_app
from app.extensions import db as _db
from app.models import User, UserRole


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


@pytest.fixture()
def admin_user(app, db):
    user = User(name="Admin Teste", email="admin@teste.com", role=UserRole.ADMIN)
    user.set_password("SenhaForte123!")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def editor_user(app, db):
    user = User(name="Editor Teste", email="editor@teste.com", role=UserRole.EDITOR)
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
