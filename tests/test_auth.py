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


def test_login_survives_concurrent_version_conflict(client, admin_user, db, app, monkeypatch):
    """
    User.version_id (controle de concorrência otimista) faz um segundo
    commit sobre a mesma linha, feito enquanto a primeira requisição
    ainda está em andamento, levantar StaleDataError. Antes, o login()
    não tratava isso: bastava duas requisições de login concorrentes
    para o mesmo usuário (duas abas, ou o navegador reenviando após uma
    falha de rede) para uma delas quebrar com erro 500 no meio do
    commit de bookkeeping (contador de tentativas / último login).
    Simulamos a corrida forçando o version_id da linha em memória a
    ficar desatualizado antes do commit do fluxo de login.
    """
    with app.app_context():
        from app.models import User

        user = User.query.filter_by(email="admin@teste.com").first()
        # Simula outra transação concorrente que já avançou o version_id
        # da linha no banco entre a leitura desta requisição e o commit.
        db.session.execute(
            User.__table__.update().where(User.id == user.id).values(version_id=user.version_id + 1)
        )
        db.session.commit()

    resp = login(client, "admin@teste.com", "SenhaForte123!")
    assert resp.status_code == 200
    assert "Visão Geral" in resp.get_data(as_text=True)
