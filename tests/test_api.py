from tests.conftest import login


def test_create_proposal_via_api(client, db):
    resp = client.post(
        "/api/v1/proposals",
        json={"name": "API Cliente", "email": "api@example.com", "phone": "67933332222"},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["public_ref"]


def test_create_proposal_via_api_missing_fields(client, db):
    resp = client.post("/api/v1/proposals", json={"name": "Sem email"})
    assert resp.status_code == 422
    data = resp.get_json()
    assert data["error"] == "validation_error"


def test_list_proposals_requires_auth(client):
    resp = client.get("/api/v1/proposals")
    assert resp.status_code in (302, 401)


def test_list_proposals_authenticated(client, admin_user, db):
    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.get("/api/v1/proposals")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "data" in data
    assert "pagination" in data


def test_get_public_site_content(client, db):
    resp = client.get("/api/v1/content/site")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "company" in data["data"]
    assert "hero" in data["data"]


def test_healthz_ignores_tenant_domain(client, db):
    """
    /healthz precisa responder mesmo com um Host desconhecido: quem chama
    esse endpoint (update.sh, systemd, monitoramento) usa o IP:porta interno
    do Gunicorn, nunca o domínio público cadastrado como TenantDomain. Se
    o gate de tenant chegasse a barrar essa rota, o endpoint responderia
    404 sempre -- fazendo o update.sh concluir (erroneamente) que todo
    deploy falhou e desfazer a atualização automaticamente.
    """
    resp = client.get("/healthz", headers={"Host": "127.0.0.1:8000"})
    assert resp.status_code == 200
