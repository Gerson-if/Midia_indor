from tests.conftest import login


def test_login_page_loads(client):
    resp = client.get("/login")
    assert resp.status_code == 200


def test_login_success(client, admin_user):
    resp = login(client, "admin@teste.com", "SenhaForte123!")
    assert resp.status_code == 200
    assert "Visão Geral" in resp.get_data(as_text=True)


def test_login_wrong_password(client, admin_user):
    resp = login(client, "admin@teste.com", "senha-errada")
    assert resp.status_code == 200
    assert "incorretos" in resp.get_data(as_text=True)


def test_account_lockout_after_failed_attempts(client, admin_user, db):
    for _ in range(5):
        login(client, "admin@teste.com", "senha-errada")

    db.session.refresh(admin_user)
    assert admin_user.is_locked is True

    resp = login(client, "admin@teste.com", "SenhaForte123!")
    assert "bloqueada" in resp.get_data(as_text=True)


def test_admin_area_requires_login(client):
    resp = client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_users_management_requires_admin_role(client, editor_user):
    login(client, "editor@teste.com", "SenhaForte123!")
    resp = client.get("/admin/usuarios")
    assert resp.status_code == 403


def test_logout_clears_session(client, admin_user):
    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.get("/logout", follow_redirects=True)
    assert resp.status_code == 200

    resp = client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 302
